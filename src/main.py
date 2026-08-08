"""
main.py
=================================================================
Command-line entry point for Gemini TTS Studio.

Run with:
    python src/main.py

Presents an interactive menu to:
    1. Generate speech from a single input file.
    2. Batch-generate speech for every ".txt" file in input/.
    3. Change the active voice (from config/voices.json presets
       or any raw Gemini voice name).
    4. Exit.
=================================================================
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

from batch import run_batch
from config import AppConfig
from exceptions import TTSStudioError
from logger import configure_logging, get_logger, log_job_result
from tts import GeminiTTSClient
from utils import output_path_for, print_progress_bar, read_text_file

APP_TITLE = "Gemini TTS Studio"


class MenuState:
    """Holds the runtime-selectable state (current voice / style)."""

    def __init__(self, default_voice: str) -> None:
        self.voice_name: str = default_voice
        self.director_notes: Optional[str] = None


def print_header() -> None:
    """Print the application title banner."""
    print("-" * 34)
    print(APP_TITLE)
    print("-" * 34)


def print_menu(state: MenuState) -> None:
    """Print the main menu, including the currently active voice."""
    print(f"\nActive voice: {state.voice_name}")
    print("1. Generate one file")
    print("2. Batch generate")
    print("3. Change voice")
    print("4. Exit")


def load_voice_presets(config: AppConfig) -> dict:
    """
    Load named voice presets from config/voices.json.

    Args:
        config: Application configuration.

    Returns:
        Dict mapping preset name -> preset details. Empty dict if the
        file is missing or invalid (a friendly warning is printed instead).
    """
    path = config.voices_config_path
    if not path.exists():
        print(f"(No voice presets found at '{path}')")
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: could not read voice presets ({exc}). Using raw voice names only.")
        return {}


def handle_single_file(config: AppConfig, client: GeminiTTSClient, state: MenuState, logger) -> None:
    """Handle menu option 1: generate speech from one input file."""
    filename = input("Enter filename (e.g. book1.txt): ").strip()
    if not filename:
        print("No filename entered.")
        return

    input_path = config.input_dir / filename
    output_path = output_path_for(input_path, config.output_dir)
    start_time = time.monotonic()

    try:
        text = read_text_file(input_path)

        def _on_progress(done: int, total: int) -> None:
            print_progress_bar(done, total, prefix="Generating")

        result = client.synthesize_to_file(
            text=text,
            output_path=output_path,
            voice_name=state.voice_name,
            director_notes=state.director_notes,
            on_progress=_on_progress,
        )
        duration = time.monotonic() - start_time
        mp3_output_path = output_path.with_suffix(".mp3")
        print(f"Completed.")
        print(f"  WAV: {output_path}")
        print(f"  MP3: {mp3_output_path}")
        log_job_result(logger, input_path.name, duration, status="SUCCESS")

    except TTSStudioError as exc:
        duration = time.monotonic() - start_time
        print(f"Error: {exc}")
        log_job_result(logger, filename, duration, status="FAILED", error=str(exc))
    except Exception as exc:  # noqa: BLE001 - guard against unexpected SDK errors
        duration = time.monotonic() - start_time
        print(f"Unexpected error: {exc}")
        log_job_result(logger, filename, duration, status="FAILED", error=str(exc))


def handle_batch(config: AppConfig, client: GeminiTTSClient, state: MenuState) -> None:
    """Handle menu option 2: batch-generate speech for every input file."""
    run_batch(
        config=config,
        client=client,
        voice_name=state.voice_name,
        director_notes=state.director_notes,
    )


def handle_change_voice(config: AppConfig, state: MenuState) -> None:
    """Handle menu option 3: change the active voice or style preset."""
    presets = load_voice_presets(config)

    if presets:
        print("\nAvailable presets:")
        for name, details in presets.items():
            print(f"  - {name} (voice: {details.get('voice_name', '?')})")

    choice = input(
        "\nEnter a preset name above, or a raw Gemini voice name (e.g. Kore): "
    ).strip()

    if not choice:
        print("No selection made. Voice unchanged.")
        return

    if choice in presets:
        state.voice_name = presets[choice].get("voice_name", state.voice_name)
        state.director_notes = presets[choice].get("director_notes")
        print(f"Voice preset set to '{choice}' (voice: {state.voice_name}).")
    else:
        state.voice_name = choice
        state.director_notes = None
        print(f"Voice set to '{choice}'.")


def main() -> None:
    """Application entry point."""
    try:
        config = AppConfig.load()
    except TTSStudioError as exc:
        print(f"Configuration error: {exc}")
        sys.exit(1)

    configure_logging(config.log_dir)
    logger = get_logger(__name__)

    try:
        client = GeminiTTSClient(config)
    except Exception as exc:  # noqa: BLE001 - guard against SDK init failures
        print(f"Failed to initialize Gemini client: {exc}")
        sys.exit(1)

    state = MenuState(default_voice=config.voice_name)

    print_header()

    while True:
        print_menu(state)
        choice = input("\nChoice: ").strip()

        if choice == "1":
            handle_single_file(config, client, state, logger)
        elif choice == "2":
            handle_batch(config, client, state)
        elif choice == "3":
            handle_change_voice(config, state)
        elif choice == "4":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1, 2, 3, or 4.")


if __name__ == "__main__":
    # Make "src" imports (config, tts, utils, ...) work when run directly
    # as `python src/main.py` from the project root.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
