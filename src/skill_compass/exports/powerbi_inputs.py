"""Read governed local pipeline outputs for the Power BI export service.

This outer input adapter owns strict file deserialization only. It must not
derive presentation rows, generate identifiers, or write JSON and Excel files.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from skill_compass.adapters.extraction_csv import read_cleaned_jobs_csv
from skill_compass.adapters.relevance_csv import (
    read_job_requirement_matches_csv,
    read_profile_relevance_csv,
    read_role_classifications_csv,
    read_seniority_classifications_csv,
)
from skill_compass.exports.powerbi_contract import PowerBiContractError
from skill_compass.schemas.analytics import (
    AnalyticsJobFact,
    AnalyticsJobSkillFact,
    AnalyticsQualityMetric,
    SkillCombinationMetric,
)
from skill_compass.schemas.classification import (
    JobProfileRelevance,
    JobRoleClassification,
    JobSeniorityClassification,
)
from skill_compass.schemas.extraction import JobRequirementMatch
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Complete typed local-input bundle
# =============================================================================


@dataclass(frozen=True, slots=True)
class PowerBiSourceInputs:
    """Bundle every governed local record required for Feature 9."""

    cleaned_jobs: tuple[CleanedJob, ...]
    role_classifications: tuple[JobRoleClassification, ...]
    seniority_classifications: tuple[JobSeniorityClassification, ...]
    relevance_classifications: tuple[JobProfileRelevance, ...]
    requirement_matches: tuple[JobRequirementMatch, ...]
    job_facts: tuple[AnalyticsJobFact, ...]
    job_skill_facts: tuple[AnalyticsJobSkillFact, ...]
    skill_combinations: tuple[SkillCombinationMetric, ...]
    analytics_quality: tuple[AnalyticsQualityMetric, ...]
    analytics_summary: dict[str, object]
    cleaning_quality: tuple[dict[str, str], ...]
    extraction_quality: tuple[dict[str, str], ...]


# =============================================================================
# Strict Feature 8 readers
# =============================================================================


ModelT = TypeVar("ModelT", bound=BaseModel)


def _read_model_csv(
    path: Path,
    model: type[ModelT],
    *,
    sequence_fields: frozenset[str] = frozenset(),
    integer_fields: frozenset[str] = frozenset(),
) -> tuple[ModelT, ...]:
    """Read one exact Pydantic CSV contract with bounded diagnostics."""
    try:
        input_file = path.open("r", encoding="utf-8", newline="")
    except OSError as error:
        raise PowerBiContractError(
            f"Power BI input could not be read: {path}"
        ) from error
    rows: list[ModelT] = []
    with input_file:
        reader = csv.DictReader(input_file, strict=True)
        if tuple(reader.fieldnames or ()) != tuple(model.model_fields):
            raise PowerBiContractError(
                f"Power BI input headers do not match: {path.name}"
            )
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise PowerBiContractError(
                    f"Power BI input row {row_number} has excess values: {path.name}"
                )
            values: dict[str, object] = dict(row)
            for field_name, value in tuple(values.items()):
                if value == "" and field_name not in sequence_fields:
                    values[field_name] = None
            for field_name in sequence_fields:
                try:
                    parsed = json.loads(str(values[field_name]))
                except json.JSONDecodeError as error:
                    raise PowerBiContractError(
                        f"Power BI input has invalid JSON: {path.name}"
                    ) from error
                if not isinstance(parsed, list):
                    raise PowerBiContractError(
                        f"Power BI input sequence is invalid: {path.name}"
                    )
                values[field_name] = tuple(parsed)
            for field_name in integer_fields:
                try:
                    values[field_name] = int(str(values[field_name]))
                except ValueError as error:
                    raise PowerBiContractError(
                        f"Power BI input integer is invalid: {path.name}"
                    ) from error
            try:
                rows.append(model.model_validate(values))
            except ValidationError as error:
                raise PowerBiContractError(
                    f"Power BI input row failed its contract: {path.name}:{row_number}"
                ) from error
    return tuple(rows)


def _read_quality_csv(path: Path) -> tuple[dict[str, str], ...]:
    """Read one standard five-column pipeline quality summary."""
    expected = (
        "metric_category",
        "metric_name",
        "metric_value",
        "metric_status",
        "metric_detail",
    )
    try:
        input_file = path.open("r", encoding="utf-8", newline="")
    except OSError as error:
        raise PowerBiContractError(
            f"quality input could not be read: {path}"
        ) from error
    with input_file:
        reader = csv.DictReader(input_file, strict=True)
        if tuple(reader.fieldnames or ()) != expected:
            raise PowerBiContractError(f"quality headers do not match: {path.name}")
        return tuple(dict(row) for row in reader)


def _read_summary(path: Path) -> dict[str, object]:
    """Read the Feature 8 reconciliation summary JSON object."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PowerBiContractError(
            f"analytics summary could not be read: {path}"
        ) from error
    if not isinstance(value, dict) or value.get("reconciliation_passed") is not True:
        raise PowerBiContractError("Feature 8 analytics reconciliation must pass")
    return value


# =============================================================================
# Public local-input boundary
# =============================================================================


def read_powerbi_source_inputs(input_dir: Path) -> PowerBiSourceInputs:
    """Read all existing Features 2–8 outputs without recalculating analytics."""
    analytics_dir = input_dir / "analytics"
    return PowerBiSourceInputs(
        cleaned_jobs=read_cleaned_jobs_csv(input_dir / "cleaned_jobs.csv"),
        role_classifications=read_role_classifications_csv(
            input_dir / "role_classification/job_role_classifications.csv"
        ),
        seniority_classifications=read_seniority_classifications_csv(
            input_dir / "seniority_classification/job_seniority_classifications.csv"
        ),
        relevance_classifications=read_profile_relevance_csv(
            input_dir / "profile_relevance/job_profile_relevance.csv"
        ),
        requirement_matches=read_job_requirement_matches_csv(
            input_dir / "skill_extraction/job_requirement_matches.csv"
        ),
        job_facts=_read_model_csv(analytics_dir / "job_facts.csv", AnalyticsJobFact),
        job_skill_facts=_read_model_csv(
            analytics_dir / "job_skill_facts.csv", AnalyticsJobSkillFact
        ),
        skill_combinations=_read_model_csv(
            analytics_dir / "skill_combinations.csv",
            SkillCombinationMetric,
            sequence_fields=frozenset({"requirement_codes"}),
            integer_fields=frozenset({"combination_size"}),
        ),
        analytics_quality=_read_model_csv(
            analytics_dir / "analytics_quality_summary.csv", AnalyticsQualityMetric
        ),
        analytics_summary=_read_summary(analytics_dir / "analytics_run_summary.json"),
        cleaning_quality=_read_quality_csv(input_dir / "data_quality_summary.csv"),
        extraction_quality=_read_quality_csv(
            input_dir / "skill_extraction/extraction_quality_summary.csv"
        ),
    )
