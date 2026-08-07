"""
batch.py
=================================================================
Batch processing: converts every ".txt" file inside the configured
input folder into a matching ".wav" file inside the output folder,
showing per-file progress and a final summary.
=================================================================
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

from config import AppConfig
from exceptions import TTSStudioError
from logger import get_logger, log_job_result
from tts import GeminiTTSClient
from utils import list_txt_files, output_path_for, print_progress_bar, read_text_file

logger = get_logger(__name__)


@dataclass
class BatchItemResult:
    """Outcome for a single file processed in a batch run."""

    filename: str
    success: bool
    output_path: str = ""
    duration_seconds: float = 0.0
    error: str = ""


def run_batch(
    config: AppConfig,
    client: GeminiTTSClient,
    voice_name: str,
    director_notes: str | None = None,
) -> List[BatchItemResult]:
    """
    Process every ".txt" file in the input folder into a ".wav" file.

    Args:
        config: Application configuration.
        client: An initialized GeminiTTSClient.
        voice_name: Voice to use for every file in the batch.
        director_notes: Optional shared style guidance for every file.

    Returns:
        List of BatchItemResult, one per input file, in processing order.
    """
    input_files = list_txt_files(config.input_dir)

    if not input_files:
        print(f"No .txt files found in '{config.input_dir}'.")
        return []

    print(f"Found {len(input_files)} file(s) to process.\n")
    results: List[BatchItemResult] = []

    for file_number, input_file in enumerate(input_files, start=1):
        print(f"[{file_number}/{len(input_files)}] {input_file.name}")
        result = _process_single_file(
            config=config,
            client=client,
            input_file=input_file,
            voice_name=voice_name,
            director_notes=director_notes,
        )
        results.append(result)
        print()  # blank line between files

    _print_summary(results)
    return results


def _process_single_file(
    config: AppConfig,
    client: GeminiTTSClient,
    input_file: Path,
    voice_name: str,
    director_notes: str | None,
) -> BatchItemResult:
    """
    Run TTS synthesis for a single input file and return its result.

    Args:
        config: Application configuration.
        client: An initialized GeminiTTSClient.
        input_file: Path to the source ".txt" file.
        voice_name: Voice to use.
        director_notes: Optional style guidance.

    Returns:
        A BatchItemResult describing success or failure.
    """
    output_path = output_path_for(input_file, config.output_dir)
    start_time = time.monotonic()

    def _on_progress(done: int, total: int) -> None:
        print_progress_bar(done, total, prefix="  Generating")

    try:
        text = read_text_file(input_file)
        result = client.synthesize_to_file(
            text=text,
            output_path=output_path,
            voice_name=voice_name,
            director_notes=director_notes,
            on_progress=_on_progress,
        )
        duration = time.monotonic() - start_time
        print(f"  Completed -> {output_path.name} ({result.duration_seconds:.1f}s audio)")
        log_job_result(logger, input_file.name, duration, status="SUCCESS")
        return BatchItemResult(
            filename=input_file.name,
            success=True,
            output_path=str(output_path),
            duration_seconds=result.duration_seconds,
        )
    except TTSStudioError as exc:
        duration = time.monotonic() - start_time
        print(f"  Failed: {exc}")
        log_job_result(logger, input_file.name, duration, status="FAILED", error=str(exc))
        return BatchItemResult(filename=input_file.name, success=False, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - guard against unexpected SDK errors
        duration = time.monotonic() - start_time
        print(f"  Unexpected error: {exc}")
        log_job_result(logger, input_file.name, duration, status="FAILED", error=str(exc))
        return BatchItemResult(filename=input_file.name, success=False, error=str(exc))


def _print_summary(results: List[BatchItemResult]) -> None:
    """Print a short success/failure summary for the whole batch."""
    succeeded = sum(1 for r in results if r.success)
    failed = len(results) - succeeded

    print("-" * 40)
    print(f"Batch complete: {succeeded} succeeded, {failed} failed.")
    if failed:
        print("Failed files:")
        for r in results:
            if not r.success:
                print(f"  - {r.filename}: {r.error}")
    print("-" * 40)
