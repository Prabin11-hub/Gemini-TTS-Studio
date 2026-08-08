"""
config.py
=================================================================
Centralized, typed configuration for Gemini TTS Studio.

All tunable values (model name, folders, retry policy, audio
format, etc.) live here and are sourced from environment
variables (loaded from a ".env" file via python-dotenv). Nothing
else in the codebase should read `os.environ` directly - this
keeps configuration in one place and easy to change.
=================================================================
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from exceptions import ConfigurationError

# Load variables from a .env file in the project root, if present.
# This must run before AppConfig.load() reads os.environ.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")


def _env_str(key: str, default: str) -> str:
    """Read a string environment variable, falling back to a default."""
    value = os.getenv(key)
    return value if value not in (None, "") else default


def _env_int(key: str, default: int) -> int:
    """Read an integer environment variable, falling back to a default."""
    raw = os.getenv(key)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    """Read a float environment variable, falling back to a default."""
    raw = os.getenv(key)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class AppConfig:
    """Immutable configuration object for the whole application."""

    # --- Credentials -------------------------------------------------
    api_key: str

    # --- Model settings ------------------------------------------------
    model_name: str = "gemini-3.1-flash-tts-preview"
    voice_name: str = "Kore"
    temperature: float = 1.0

    # --- Folder locations ------------------------------------------------
    project_root: Path = field(default_factory=lambda: _PROJECT_ROOT)
    input_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "input")
    output_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "output")
    log_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "logs")
    voices_config_path: Path = field(
        default_factory=lambda: _PROJECT_ROOT / "config" / "voices.json"
    )

    # --- Retry / networking ------------------------------------------------
    retry_count: int = 3
    retry_delay_seconds: float = 2.0
    request_timeout: int = 60

    # --- Text chunking (Gemini TTS has a 32k token context window and
    #     quality can drift on very long single generations) ------------
    max_chunk_chars: int = 1800

    # --- Audio output format (PCM produced by Gemini TTS) ------------------
    sample_rate: int = 24000
    channels: int = 1
    sample_width: int = 2 # bytes per sample (16-bit PCM)
    mp3_bitrate: int = 128

    @classmethod
    def load(cls) -> "AppConfig":
        """
        Build an AppConfig instance from environment variables.

        Raises:
            ConfigurationError: if a required value (API key) is missing.
        """
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ConfigurationError(
                "GEMINI_API_KEY is not set. Copy '.env.example' to '.env' "
                "and add your Gemini API key from https://aistudio.google.com/apikey."
            )

        config = cls(
            api_key=api_key,
            model_name=_env_str("MODEL_NAME", "gemini-3.1-flash-tts-preview"),
            voice_name=_env_str("VOICE_NAME", "Kore"),
            temperature=_env_float("TEMPERATURE", 1.0),
            retry_count=_env_int("RETRY_COUNT", 3),
            retry_delay_seconds=_env_float("RETRY_DELAY_SECONDS", 2.0),
            request_timeout=_env_int("REQUEST_TIMEOUT", 60),
            max_chunk_chars=_env_int("MAX_CHUNK_CHARS", 1800),
            mp3_bitrate=_env_int("MP3_BITRATE", 128),
        )
        config.ensure_directories()
        return config

    def ensure_directories(self) -> None:
        """Create the input/output/logs folders automatically if missing."""
        for directory in (self.input_dir, self.output_dir, self.log_dir):
            directory.mkdir(parents=True, exist_ok=True)
