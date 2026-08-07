"""
utils.py
=================================================================
General-purpose helper functions for Gemini TTS Studio, grouped
into: file helpers, folder helpers, audio helpers, and validation.
=================================================================
"""

from __future__ import annotations

import re
import sys
import wave
from pathlib import Path
from typing import List

from exceptions import AudioProcessingError, EmptyTextError, FileValidationError

# =====================================================================
# File helpers
# =====================================================================


def read_text_file(file_path: Path) -> str:
    """
    Read a UTF-8 text file and return its contents.

    Args:
        file_path: Path to the .txt file.

    Returns:
        The file's text content, whitespace-trimmed.

    Raises:
        FileValidationError: if the file does not exist or cannot be read.
        EmptyTextError: if the file contains no usable text.
    """
    if not file_path.exists():
        raise FileValidationError(f"Input file not found: {file_path}")
    if not file_path.is_file():
        raise FileValidationError(f"Not a file: {file_path}")

    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise FileValidationError(
            f"'{file_path.name}' is not valid UTF-8 text: {exc}"
        ) from exc

    text = text.strip()
    if not text:
        raise EmptyTextError(f"'{file_path.name}' is empty.")
    return text


def list_txt_files(folder: Path) -> List[Path]:
    """
    List every ".txt" file directly inside a folder, sorted by name.

    Args:
        folder: Directory to scan.

    Returns:
        Sorted list of Path objects pointing to ".txt" files.
    """
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".txt")


def output_path_for(input_file: Path, output_dir: Path) -> Path:
    """
    Compute the output ".wav" path that matches an input file's name.

    Example: input/book1.txt -> output/book1.wav

    Args:
        input_file: The source ".txt" file.
        output_dir: Destination folder for audio.

    Returns:
        Path to the corresponding ".wav" file.
    """
    safe_stem = sanitize_filename(input_file.stem)
    return output_dir / f"{safe_stem}.wav"


def sanitize_filename(name: str) -> str:
    """
    Strip characters that are invalid in Windows filenames.

    Args:
        name: Proposed filename (without extension).

    Returns:
        A filesystem-safe version of the name.
    """
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name).strip()
    return cleaned or "untitled"


# =====================================================================
# Folder helpers
# =====================================================================


def ensure_dir(path: Path) -> Path:
    """
    Create a directory (and parents) if it does not already exist.

    Args:
        path: Directory to create.

    Returns:
        The same path, for chaining.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


# =====================================================================
# Text chunking (keeps requests under the model's context window and
# avoids audio-quality drift on very long single generations)
# =====================================================================


def chunk_text(text: str, max_chars: int) -> List[str]:
    """
    Split text into chunks no longer than `max_chars`, breaking on
    sentence or paragraph boundaries where possible so speech does
    not get cut mid-sentence.

    Args:
        text: Full input text (may contain Unicode, Hindi, etc.).
        max_chars: Maximum characters allowed per chunk.

    Returns:
        List of text chunks, each <= max_chars (best effort).
    """
    if len(text) <= max_chars:
        return [text]

    # Split into sentences on '.', '?', '!', and Hindi danda '।' followed
    # by whitespace, while keeping the punctuation attached to the sentence.
    sentence_pattern = re.compile(r"(?<=[.!?।])\s+")
    sentences = sentence_pattern.split(text)

    chunks: List[str] = []
    current = ""

    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence

        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = sentence
        else:
            # A single sentence longer than max_chars: hard-split it.
            for i in range(0, len(sentence), max_chars):
                chunks.append(sentence[i : i + max_chars])
            current = ""

    if current:
        chunks.append(current)

    return chunks or [text]


# =====================================================================
# Audio helpers
# =====================================================================


def write_wave_file(
    output_path: Path,
    pcm_data: bytes,
    channels: int,
    sample_rate: int,
    sample_width: int,
) -> None:
    """
    Write raw PCM audio bytes to a single ".wav" file.

    Args:
        output_path: Destination ".wav" file path.
        pcm_data: Concatenated raw PCM audio bytes (all chunks combined).
        channels: Number of audio channels (Gemini TTS outputs mono = 1).
        sample_rate: Sample rate in Hz (Gemini TTS outputs 24000).
        sample_width: Bytes per sample (Gemini TTS outputs 16-bit = 2).

    Raises:
        AudioProcessingError: if the file cannot be written.
    """
    if not pcm_data:
        raise AudioProcessingError("No audio data was generated to write.")

    try:
        ensure_dir(output_path.parent)
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
    except (OSError, wave.Error) as exc:
        raise AudioProcessingError(f"Failed to write '{output_path}': {exc}") from exc


def audio_duration_seconds(pcm_byte_count: int, sample_rate: int, sample_width: int, channels: int) -> float:
    """
    Estimate audio duration, in seconds, from raw PCM byte count.

    Args:
        pcm_byte_count: Number of raw PCM bytes.
        sample_rate: Sample rate in Hz.
        sample_width: Bytes per sample.
        channels: Number of channels.

    Returns:
        Estimated duration in seconds.
    """
    bytes_per_second = sample_rate * sample_width * channels
    if bytes_per_second == 0:
        return 0.0
    return pcm_byte_count / bytes_per_second


# =====================================================================
# Validation
# =====================================================================


def validate_api_key(api_key: str) -> None:
    """
    Perform a lightweight sanity check on the configured API key.

    Args:
        api_key: The Gemini API key string.

    Raises:
        FileValidationError: if the key looks obviously invalid.
    """
    if not api_key or api_key.strip() in ("", "your_gemini_api_key_here"):
        raise FileValidationError(
            "No valid GEMINI_API_KEY configured. Edit your '.env' file."
        )


# =====================================================================
# Progress display
# =====================================================================


def print_progress_bar(current: int, total: int, prefix: str = "Generating", bar_length: int = 30) -> None:
    """
    Render a simple terminal progress bar, e.g.:

        Generating... [######......] 50%

    Args:
        current: Number of steps completed so far.
        total: Total number of steps.
        prefix: Text shown before the bar.
        bar_length: Width of the bar, in characters.
    """
    total = max(total, 1)
    fraction = min(max(current / total, 0.0), 1.0)
    filled = int(bar_length * fraction)
    bar = "█" * filled + "." * (bar_length - filled)
    percent = int(fraction * 100)

    sys.stdout.write(f"\r{prefix}... [{bar}] {percent}%")
    sys.stdout.flush()

    if current >= total:
        sys.stdout.write("\n")
        sys.stdout.flush()
