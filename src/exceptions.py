"""
exceptions.py
=================================================================
Custom exception hierarchy for Gemini TTS Studio.

Using dedicated exception types (instead of bare `Exception`)
lets the rest of the application catch failures precisely and
present friendly, actionable error messages to the user.
=================================================================
"""

from __future__ import annotations


class TTSStudioError(Exception):
    """Base class for every error raised by Gemini TTS Studio."""


class ConfigurationError(TTSStudioError):
    """Raised when required configuration (e.g. API key) is missing or invalid."""


class FileValidationError(TTSStudioError):
    """Raised when an input file is missing, unreadable, or otherwise invalid."""


class EmptyTextError(FileValidationError):
    """Raised when an input file contains no usable text."""


class APIRequestError(TTSStudioError):
    """Raised when a call to the Gemini API fails (network, HTTP, or SDK error)."""


class RetryExhaustedError(APIRequestError):
    """Raised when every configured retry attempt has failed."""


class AudioProcessingError(TTSStudioError):
    """Raised when audio bytes cannot be decoded, combined, or written to disk."""


class VoiceNotFoundError(ConfigurationError):
    """Raised when a requested voice preset does not exist in config/voices.json."""
