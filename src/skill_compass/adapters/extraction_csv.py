"""Read cleaned-job CSV records and write stable extraction CSV outputs.

This outer adapter translates typed storage boundaries only and must not match
requirements, calculate demand, regenerate Feature 2 data, or render charts.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from pydantic import ValidationError

from skill_compass.adapters.csv import CLEANED_JOB_COLUMNS, write_model_csv
from skill_compass.extraction.errors import ExtractionInputError
from skill_compass.schemas.extraction import (
    ExtractionQualityMetric,
    ExtractionRunResult,
    JobExtractionSummary,
    JobRequirementMatch,
    RequirementEvidence,
    SkillDemandSummary,
)
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Cleaned-job CSV input
# =============================================================================


SEQUENCE_COLUMNS = frozenset(
    {
        "bullet_points_clean",
        "employment_type_codes",
        "quality_flags",
        "fallback_fields_used",
    }
)
OPTIONAL_COLUMNS = frozenset(
    {
        "company_name_raw",
        "company_name_clean",
        "summary_text_clean",
        "description_text_clean",
        "source_role_code_raw",
        "classification_raw",
        "classification_code_raw",
        "subclassification_raw",
        "subclassification_code_raw",
        "location_raw",
        "country_code",
        "state_code",
        "state_name",
        "city_name",
        "suburb_name",
        "salary_label_raw",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_period",
        "listing_date",
        "expires_at",
        "scraped_at",
    }
)


def parse_sequence_cell(value: str, row_number: int, column: str) -> tuple[str, ...]:
    """Parse one JSON list emitted by the Feature 2 stable CSV writer."""
    if not value:
        return ()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ExtractionInputError(
            f"cleaned CSV row {row_number} has invalid {column} JSON"
        ) from error
    if not isinstance(parsed, list) or any(
        not isinstance(item, str) for item in parsed
    ):
        raise ExtractionInputError(
            f"cleaned CSV row {row_number} has invalid {column} values"
        )
    return tuple(parsed)


def deserialize_cleaned_row(row: dict[str, str], row_number: int) -> CleanedJob:
    """Convert one Feature 2 CSV row back to its strict typed contract."""
    values: dict[str, object] = {}
    for column in CLEANED_JOB_COLUMNS:
        value = row[column]
        if column in SEQUENCE_COLUMNS:
            values[column] = parse_sequence_cell(value, row_number, column)
        elif column == "source_row_number":
            try:
                values[column] = int(value)
            except ValueError as error:
                raise ExtractionInputError(
                    f"cleaned CSV row {row_number} has invalid source_row_number"
                ) from error
        elif column == "analytically_eligible":
            normalized = value.casefold()
            if normalized not in {"true", "false"}:
                raise ExtractionInputError(
                    f"cleaned CSV row {row_number} has invalid analytically_eligible"
                )
            values[column] = normalized == "true"
        elif column in OPTIONAL_COLUMNS and value == "":
            values[column] = None
        else:
            values[column] = value
    try:
        return CleanedJob.model_validate(values)
    except ValidationError as error:
        raise ExtractionInputError(
            f"cleaned CSV row {row_number} failed the CleanedJob contract"
        ) from error


def read_cleaned_jobs_csv(path: Path) -> tuple[CleanedJob, ...]:
    """Read exactly the stable Feature 2 cleaned-job CSV contract."""
    try:
        input_file = path.open("r", encoding="utf-8", newline="")
    except OSError as error:
        raise ExtractionInputError(
            f"cleaned input could not be read: {path}"
        ) from error

    with input_file:
        reader = csv.DictReader(input_file, strict=True)
        headers = tuple(reader.fieldnames or ())
        if headers != CLEANED_JOB_COLUMNS:
            raise ExtractionInputError(
                "cleaned CSV headers do not match the Feature 2 CleanedJob contract"
            )
        jobs = []
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ExtractionInputError(
                    f"cleaned CSV row {row_number} has more values than headers"
                )
            jobs.append(deserialize_cleaned_row(dict(row), row_number))

    return tuple(
        sorted(
            jobs,
            key=lambda job: (
                job.source_code,
                job.source_row_number,
                job.source_job_id,
            ),
        )
    )


# =============================================================================
# Stable extraction CSV output
# =============================================================================


JOB_REQUIREMENT_MATCH_COLUMNS = tuple(JobRequirementMatch.model_fields)
REQUIREMENT_EVIDENCE_COLUMNS = tuple(RequirementEvidence.model_fields)
JOB_EXTRACTION_SUMMARY_COLUMNS = tuple(JobExtractionSummary.model_fields)
SKILL_DEMAND_SUMMARY_COLUMNS = tuple(SkillDemandSummary.model_fields)
EXTRACTION_QUALITY_COLUMNS = tuple(ExtractionQualityMetric.model_fields)


def write_extraction_outputs(
    output_dir: Path, result: ExtractionRunResult
) -> dict[str, int]:
    """Write all five approved extraction CSV outputs and return row counts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "job_requirement_matches.csv": (
            result.job_requirement_matches,
            JOB_REQUIREMENT_MATCH_COLUMNS,
        ),
        "requirement_evidence.csv": (
            result.evidence,
            REQUIREMENT_EVIDENCE_COLUMNS,
        ),
        "job_extraction_summary.csv": (
            result.job_summaries,
            JOB_EXTRACTION_SUMMARY_COLUMNS,
        ),
        "skill_demand_summary.csv": (
            result.skill_demand,
            SKILL_DEMAND_SUMMARY_COLUMNS,
        ),
        "extraction_quality_summary.csv": (
            result.quality_metrics,
            EXTRACTION_QUALITY_COLUMNS,
        ),
    }
    return {
        filename: write_model_csv(output_dir / filename, records, columns)
        for filename, (records, columns) in outputs.items()
    }
