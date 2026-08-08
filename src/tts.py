"""
tts.py
=================================================================
Wrapper around Google's Gemini TTS model (via the google-genai
"Interactions" API) that turns text into a single WAV file.

Key design points:
- Uses `client.interactions.create(..., stream=True)`, the
  officially recommended streaming path for `gemini-3.1-flash-tts-preview`,
  so progress can be reported as audio is generated.
- Long scripts are split into safe-sized chunks (see utils.chunk_text)
  to respect the model's context window and avoid quality drift on
  very long single generations. Each chunk's raw PCM audio is
  collected in memory and concatenated - the app NEVER writes one
  WAV file per chunk, only a single final file.
- Every network call is wrapped in automatic retry logic (tenacity)
  to recover from transient failures, including the documented
  occasional 5xx errors from the TTS model.
=================================================================
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Callable, List, Optional

from google import genai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import AppConfig
from exceptions import APIRequestError, AudioProcessingError, RetryExhaustedError
from logger import get_logger
from utils import (
    audio_duration_seconds,
    chunk_text,
    write_mp3_file,
    write_wave_file,
)

logger = get_logger(__name__)

# Progress callback signature: (chunks_done, chunks_total) -> None
ProgressCallback = Callable[[int, int], None]


@dataclass
class SynthesisResult:
    """Outcome of a text-to-speech synthesis job."""

    output_path: str
    duration_seconds: float
    chunk_count: int


class GeminiTTSClient:
    """High-level client that turns text into a single spoken WAV file."""

    def __init__(self, config: AppConfig) -> None:
        """
        Initialize the underlying Gemini GenAI client.

        Args:
            config: Application configuration (API key, model, retry policy...).
        """
        self.config = config
        self._client = genai.Client(api_key=config.api_key)

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def synthesize_to_file(
        self,
        text: str,
        output_path,
        voice_name: Optional[str] = None,
        director_notes: Optional[str] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> SynthesisResult:
        """
        Convert text into speech and save it as a single WAV file.

        Args:
            text: The full text to speak (any length; will be chunked).
            output_path: Destination ".wav" path.
            voice_name: Gemini voice name (falls back to config default).
            director_notes: Optional style/performance guidance prepended
                to the transcript (e.g. "Style: warm audiobook narrator...").
            on_progress: Optional callback invoked as (chunks_done, chunks_total).

        Returns:
            SynthesisResult describing the generated file.

        Raises:
            AudioProcessingError: if no audio could be generated.
            RetryExhaustedError: if the API kept failing after every retry.
        """
        voice = voice_name or self.config.voice_name
        chunks = chunk_text(text, self.config.max_chunk_chars)
        total_chunks = len(chunks)

        logger.info(
            "Starting synthesis: voice=%s chunks=%d output=%s", voice, total_chunks, output_path
        )

        all_pcm_bytes: List[bytes] = []

        for index, chunk in enumerate(chunks, start=1):
            prompt = self._build_prompt(chunk, director_notes)
            pcm_bytes = self._synthesize_chunk(prompt=prompt, voice=voice)
            all_pcm_bytes.append(pcm_bytes)

            if on_progress:
                on_progress(index, total_chunks)

        combined_pcm = b"".join(all_pcm_bytes)
        write_wave_file(
            output_path=output_path,
            pcm_data=combined_pcm,
            channels=self.config.channels,
            sample_rate=self.config.sample_rate,
            sample_width=self.config.sample_width,
        )

        mp3_output_path = output_path.with_suffix(".mp3")

        write_mp3_file(
            output_path=mp3_output_path,
            pcm_data=combined_pcm,
            channels=self.config.channels,
            sample_rate=self.config.sample_rate,
            sample_width=self.config.sample_width,
            bitrate=self.config.mp3_bitrate,
        )
    
        duration = audio_duration_seconds(
            pcm_byte_count=len(combined_pcm),
            sample_rate=self.config.sample_rate,
            sample_width=self.config.sample_width,
            channels=self.config.channels,
        )

        logger.info("Synthesis complete: output=%s duration=%.2fs", output_path, duration)

        return SynthesisResult(
            output_path=str(output_path),
            duration_seconds=duration,
            chunk_count=total_chunks,
        )

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _build_prompt(chunk: str, director_notes: Optional[str]) -> str:
        """
        Combine optional director's notes with the transcript chunk.

        Args:
            chunk: The text to speak.
            director_notes: Optional style guidance.

        Returns:
            The final prompt sent to the TTS model.
        """
        if not director_notes:
            return chunk
        return (
            f"{director_notes}\n\n"
            f"Synthesize the following transcript as speech, in the style "
            f"described above:\n\n{chunk}"
        )

    def _synthesize_chunk(self, prompt: str, voice: str) -> bytes:
        """
        Call the Gemini TTS API for a single chunk, with automatic retry.

        Args:
            prompt: Text (optionally with director's notes) to synthesize.
            voice: Gemini voice name to use.

        Returns:
            Raw PCM audio bytes for this chunk.

        Raises:
            RetryExhaustedError: if every retry attempt fails.
            AudioProcessingError: if the API returns no audio data.
        """
        retrying_call = self._build_retrying_caller()
        try:
            return retrying_call(prompt, voice)
        except APIRequestError as exc:
            raise RetryExhaustedError(
                f"Gemini TTS request failed after {self.config.retry_count} attempt(s): {exc}"
            ) from exc

    def _build_retrying_caller(self):
        """Build a tenacity-wrapped callable that performs one streaming request."""

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.config.retry_count),
            wait=wait_exponential(multiplier=self.config.retry_delay_seconds, min=1, max=30),
            retry=retry_if_exception_type(APIRequestError),
        )
        def _call(prompt: str, voice: str) -> bytes:
            return self._stream_request(prompt=prompt, voice=voice)

        return _call

    def _stream_request(self, prompt: str, voice: str) -> bytes:
        """
        Perform a single streaming TTS request and collect its audio bytes.

        Args:
            prompt: Text to synthesize.
            voice: Gemini voice name.

        Returns:
            Concatenated raw PCM bytes decoded from the stream.

        Raises:
            APIRequestError: on any network/SDK/HTTP failure (retried by caller).
            AudioProcessingError: if the stream yields no audio at all.
        """
        try:
            stream = self._client.interactions.create(
                model=self.config.model_name,
                input=prompt,
                response_format={"type": "audio"},
                generation_config={"speech_config": [{"voice": voice}]},
                stream=True,
            )

            audio_parts: List[bytes] = []
            for event in stream:
                if getattr(event, "event_type", None) != "step.delta":
                    continue
                delta = getattr(event, "delta", None)
                if delta is not None and getattr(delta, "type", None) == "audio":
                    audio_parts.append(base64.b64decode(delta.data))

            if not audio_parts:
                raise AudioProcessingError(
                    "Gemini TTS returned no audio data for this chunk."
                )

            return b"".join(audio_parts)

        except AudioProcessingError:
            raise
        except Exception as exc:  # noqa: BLE001 - re-raised as a typed API error
            logger.warning("Gemini TTS request failed, will retry if possible: %s", exc)
            raise APIRequestError(str(exc)) from exc
