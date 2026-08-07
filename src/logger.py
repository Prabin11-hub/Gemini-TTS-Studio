"""
logger.py
=================================================================
Application-wide logging configuration for Gemini TTS Studio.

Writes structured log entries (timestamp, filename, duration,
status, errors) to "logs/app.log" using a rotating file handler,
and mirrors warnings/errors to the console so the CLI user gets
immediate feedback without cluttering stdout with debug noise.
=================================================================
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(log_dir: Path) -> None:
    """
    Configure the root logger once for the whole application.

    Args:
        log_dir: Directory where "app.log" will be created.
    """
    global _configured
    if _configured:
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=5 * 1024 * 1024,  # 5 MB per file
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a module-level logger.

    Args:
        name: Usually `__name__` of the calling module.

    Returns:
        A configured `logging.Logger` instance.
    """
    return logging.getLogger(name)


def log_job_result(
    logger: logging.Logger,
    filename: str,
    duration_seconds: float,
    status: str,
    error: str | None = None,
) -> None:
    """
    Emit a single structured log line for a completed TTS job.

    Args:
        logger: The logger to write to.
        filename: Name of the input/output file processed.
        duration_seconds: How long the job took, in seconds.
        status: "SUCCESS" or "FAILED".
        error: Optional error message when status is "FAILED".
    """
    message = f"file={filename} duration={duration_seconds:.2f}s status={status}"
    if error:
        message += f" error={error}"
        logger.error(message)
    else:
        logger.info(message)
