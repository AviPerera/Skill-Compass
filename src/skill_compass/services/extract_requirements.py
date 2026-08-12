"""Orchestrate cleaned-CSV requirement extraction and stable output writing.

This application service coordinates adapters and the reusable engine but must
not regenerate Feature 2 data, implement matching rules, or render demo charts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skill_compass.adapters.extraction_csv import (
    read_cleaned_jobs_csv,
    write_extraction_outputs,
)
from skill_compass.extraction.dictionary import load_requirement_dictionary
from skill_compass.extraction.errors import ExtractionInputError
from skill_compass.extraction.profile import load_extraction_profile
from skill_compass.extraction.service import extract_requirements
from skill_compass.schemas.extraction import ExtractionRunResult
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Typed file-boundary result
# =============================================================================


FEATURE_2_CLEANING_COMMAND = (
    "uv run skill-compass clean-csv "
    "--input data/private/adelaide_146_jobs_raw.csv "
    "--mapping sources/apify_seek_current/source_mapping.yaml "
    "--output-dir data/processed/demo_2"
)


@dataclass(frozen=True, slots=True)
class ExtractionOutputFileSummary:
    """Describe one generated extraction CSV and its data-row count."""

    path: Path
    row_count: int


@dataclass(frozen=True, slots=True)
class ExtractionCsvRunResult:
    """Return typed extraction results plus generated CSV file evidence."""

    input_path: Path
    profile_path: Path
    dictionary_path: Path
    output_dir: Path
    cleaned_jobs: tuple[CleanedJob, ...]
    extraction: ExtractionRunResult
    output_files: tuple[ExtractionOutputFileSummary, ...]


def process_cleaned_csv(
    *,
    input_path: Path,
    profile_path: Path,
    dictionary_path: Path,
    output_dir: Path,
) -> ExtractionCsvRunResult:
    """Load cleaned jobs and configuration, extract, reconcile, and write CSVs."""
    if not input_path.is_file():
        raise ExtractionInputError(
            f"cleaned Feature 2 input is missing: {input_path}. "
            f"Create it first with: {FEATURE_2_CLEANING_COMMAND}"
        )
    profile = load_extraction_profile(profile_path)
    dictionary = load_requirement_dictionary(dictionary_path, profile)
    cleaned_jobs = read_cleaned_jobs_csv(input_path)
    result = extract_requirements(cleaned_jobs, profile, dictionary)
    output_counts = write_extraction_outputs(output_dir, result)
    output_files = tuple(
        ExtractionOutputFileSummary(output_dir / filename, row_count)
        for filename, row_count in output_counts.items()
    )
    return ExtractionCsvRunResult(
        input_path=input_path,
        profile_path=profile_path,
        dictionary_path=dictionary_path,
        output_dir=output_dir,
        cleaned_jobs=cleaned_jobs,
        extraction=result,
        output_files=output_files,
    )
