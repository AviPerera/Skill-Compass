"""Validate deterministic Feature 3 CSV processing using a sanitised fixture."""

import csv
from pathlib import Path

from skill_compass.adapters.extraction_csv import (
    EXTRACTION_QUALITY_COLUMNS,
    JOB_EXTRACTION_SUMMARY_COLUMNS,
    JOB_REQUIREMENT_MATCH_COLUMNS,
    REQUIREMENT_EVIDENCE_COLUMNS,
    SKILL_DEMAND_SUMMARY_COLUMNS,
    read_cleaned_jobs_csv,
)
from skill_compass.services.extract_requirements import process_cleaned_csv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/cleaned_jobs.csv"
PROFILE_PATH = PROJECT_ROOT / "profiles/data_analytics/profile.yaml"
DICTIONARY_PATH = PROJECT_ROOT / "profiles/data_analytics/requirements.csv"
EXPECTED_FILES = {
    "job_requirement_matches.csv": JOB_REQUIREMENT_MATCH_COLUMNS,
    "requirement_evidence.csv": REQUIREMENT_EVIDENCE_COLUMNS,
    "job_extraction_summary.csv": JOB_EXTRACTION_SUMMARY_COLUMNS,
    "skill_demand_summary.csv": SKILL_DEMAND_SUMMARY_COLUMNS,
    "extraction_quality_summary.csv": EXTRACTION_QUALITY_COLUMNS,
}


def read_header(path: Path) -> tuple[str, ...]:
    """Read one UTF-8 output header using the standard CSV parser."""
    with path.open("r", encoding="utf-8", newline="") as input_file:
        return tuple(next(csv.reader(input_file)))


def process(output_dir: Path):
    """Run the reusable Feature 3 file boundary against the sanitised fixture."""
    return process_cleaned_csv(
        input_path=FIXTURE_PATH,
        profile_path=PROFILE_PATH,
        dictionary_path=DICTIONARY_PATH,
        output_dir=output_dir,
    )


def test_cleaned_fixture_reads_as_typed_feature_2_records() -> None:
    jobs = read_cleaned_jobs_csv(FIXTURE_PATH)

    assert len(jobs) == 4
    assert jobs[0].source_job_id == "fixture-201"
    assert jobs[0].bullet_points_clean == (
        "SQL Server and Tableau",
        "No R experience required.",
    )
    assert jobs[-1].analytically_eligible is False


def test_fixture_processes_end_to_end_and_writes_stable_outputs(
    tmp_path: Path,
) -> None:
    result = process(tmp_path)

    assert result.extraction.reconciliation_passed is True
    assert len(result.extraction.job_requirement_matches) == 13
    assert len(result.extraction.evidence) == 16
    assert {item.path.name: item.row_count for item in result.output_files} == {
        "job_requirement_matches.csv": 13,
        "requirement_evidence.csv": 16,
        "job_extraction_summary.csv": 4,
        "skill_demand_summary.csv": 31,
        "extraction_quality_summary.csv": len(result.extraction.quality_metrics),
    }
    for filename, expected_columns in EXPECTED_FILES.items():
        output_path = tmp_path / filename
        assert output_path.is_file()
        assert read_header(output_path) == expected_columns
        output_path.read_bytes().decode("utf-8")


def test_repeated_processing_is_byte_deterministic(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    process(first_dir)
    process(second_dir)

    for filename in EXPECTED_FILES:
        assert (first_dir / filename).read_bytes() == (
            second_dir / filename
        ).read_bytes()


def test_outputs_exclude_non_content_and_full_descriptions(tmp_path: Path) -> None:
    process(tmp_path)
    combined_output = b"".join(
        (tmp_path / filename).read_bytes() for filename in EXPECTED_FILES
    ).decode("utf-8")

    assert "https://example.test/jobs" not in combined_output
    assert "Fictional Insights" not in combined_output
    assert (
        "Build dashboards with Excel and stakeholder management." not in combined_output
    )
    assert (
        "Power BI is not required. Produce data storytelling outputs."
        not in combined_output
    )
    assert "contact_email" not in combined_output
    assert "tracking" not in combined_output
