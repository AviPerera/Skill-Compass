"""Validate deterministic end-to-end processing using only a fictional CSV fixture."""

import csv
from pathlib import Path

from skill_compass.adapters.csv import (
    CLEANED_JOB_COLUMNS,
    MAPPED_JOB_COLUMNS,
    QUALITY_METRIC_COLUMNS,
    REJECTED_RECORD_COLUMNS,
)
from skill_compass.services.clean_csv import process_csv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/apify_seek_jobs.csv"
MAPPING_PATH = PROJECT_ROOT / "sources/apify_seek_current/source_mapping.yaml"
EXPECTED_FILES = {
    "mapped_jobs.csv": MAPPED_JOB_COLUMNS,
    "cleaned_jobs.csv": CLEANED_JOB_COLUMNS,
    "rejected_jobs.csv": REJECTED_RECORD_COLUMNS,
    "data_quality_summary.csv": QUALITY_METRIC_COLUMNS,
}


def read_header(path: Path) -> tuple[str, ...]:
    """Read one generated CSV header using its documented UTF-8 encoding."""
    with path.open("r", encoding="utf-8", newline="") as input_file:
        return tuple(next(csv.reader(input_file)))


def test_fixture_processes_end_to_end_and_reconciles(tmp_path: Path) -> None:
    output_dir = tmp_path / "first"

    result = process_csv(
        input_path=FIXTURE_PATH,
        mapping_path=MAPPING_PATH,
        output_dir=output_dir,
    )

    assert result.input_rows == 10
    assert result.mapping_success_rows == 7
    assert result.structurally_rejected_rows == 3
    assert result.duplicate_same_content_rows == 1
    assert result.duplicate_conflicting_content_rows == 1
    assert len(result.cleaned_jobs) == 5
    assert result.total_rejected_rows == 5
    assert result.analytically_eligible_rows == 4
    assert result.analytically_ineligible_rows == 1
    assert result.reconciliation_passed is True

    for filename, expected_columns in EXPECTED_FILES.items():
        output_path = output_dir / filename
        assert output_path.is_file()
        assert read_header(output_path) == expected_columns
        output_path.read_bytes().decode("utf-8")


def test_repeated_fixture_processing_is_byte_deterministic(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    process_csv(
        input_path=FIXTURE_PATH,
        mapping_path=MAPPING_PATH,
        output_dir=first_dir,
    )
    process_csv(
        input_path=FIXTURE_PATH,
        mapping_path=MAPPING_PATH,
        output_dir=second_dir,
    )

    for filename in EXPECTED_FILES:
        assert (first_dir / filename).read_bytes() == (
            second_dir / filename
        ).read_bytes()


def test_sensitive_fixture_values_are_excluded_from_outputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    process_csv(
        input_path=FIXTURE_PATH,
        mapping_path=MAPPING_PATH,
        output_dir=output_dir,
    )

    combined_output = b"".join(
        (output_dir / filename).read_bytes() for filename in EXPECTED_FILES
    ).decode("utf-8")
    assert "@example.test" not in combined_output
    assert "fixture-token" not in combined_output
    assert "fixture-track" not in combined_output
