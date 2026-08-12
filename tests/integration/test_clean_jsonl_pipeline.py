"""Validate Feature 2 processing using only a fictional JSONL fixture."""

from pathlib import Path

from skill_compass.adapters.csv import (
    CLEANED_JOB_COLUMNS,
    MAPPED_JOB_COLUMNS,
    QUALITY_METRIC_COLUMNS,
    REJECTED_RECORD_COLUMNS,
)
from skill_compass.services.clean_jsonl import process_jsonl

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/apify_seek_jobs.jsonl"
MAPPING_PATH = PROJECT_ROOT / "sources/apify_seek_current/source_mapping.yaml"
EXPECTED_FILES = {
    "mapped_jobs.csv": MAPPED_JOB_COLUMNS,
    "cleaned_jobs.csv": CLEANED_JOB_COLUMNS,
    "rejected_jobs.csv": REJECTED_RECORD_COLUMNS,
    "data_quality_summary.csv": QUALITY_METRIC_COLUMNS,
}


def test_jsonl_processes_through_existing_feature_2_pipeline(tmp_path: Path) -> None:
    result = process_jsonl(
        input_path=FIXTURE_PATH,
        mapping_path=MAPPING_PATH,
        output_dir=tmp_path / "outputs",
    )

    assert result.input_rows == 4
    assert result.mapping_success_rows == 3
    assert result.structurally_rejected_rows == 1
    assert result.duplicate_same_content_rows == 1
    assert result.duplicate_conflicting_content_rows == 0
    assert len(result.cleaned_jobs) == 2
    assert result.total_rejected_rows == 2
    assert result.reconciliation_passed is True
    assert result.cleaned_jobs[1].source_job_id == "2002"
    assert "source_job_id:raw/detail/id" in result.cleaned_jobs[1].fallback_fields_used
    assert {output.path.name for output in result.output_files} == set(EXPECTED_FILES)


def test_jsonl_processing_is_deterministic_and_excludes_sensitive_values(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    process_jsonl(
        input_path=FIXTURE_PATH,
        mapping_path=MAPPING_PATH,
        output_dir=first_dir,
    )
    process_jsonl(
        input_path=FIXTURE_PATH,
        mapping_path=MAPPING_PATH,
        output_dir=second_dir,
    )

    for filename in EXPECTED_FILES:
        assert (first_dir / filename).read_bytes() == (
            second_dir / filename
        ).read_bytes()

    combined_output = b"".join(
        (first_dir / filename).read_bytes() for filename in EXPECTED_FILES
    ).decode("utf-8")
    assert "private-jsonl@example.test" not in combined_output
    assert "private-salary@example.test" not in combined_output
    assert "another-private@example.test" not in combined_output
    assert "fixture-jsonl-token" not in combined_output
