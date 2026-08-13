"""Read upstream classifier CSVs and write stable relevance outputs.

This outer adapter owns typed CSV translation only. It must not score evidence,
make relevance decisions, render charts, or expose full job descriptions.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from skill_compass.adapters.csv import write_model_csv
from skill_compass.classification.errors import RelevanceInputError
from skill_compass.schemas.classification import (
    JobProfileRelevance,
    JobRoleClassification,
    JobSeniorityClassification,
    ProfileRelevanceDiagnostic,
    ProfileRelevanceEvidence,
    ProfileRelevanceReviewQueueItem,
    ProfileRelevanceRunResult,
    ProfileRelevanceSummary,
)
from skill_compass.schemas.extraction import JobRequirementMatch

# =============================================================================
# Strict upstream CSV readers
# =============================================================================


ModelT = TypeVar("ModelT", bound=BaseModel)
SEQUENCE_FIELDS = frozenset(
    {
        "matched_sections",
        "matched_aliases",
        "quality_flags",
        "relevance_quality_flags",
    }
)
OPTIONAL_FIELDS = frozenset(
    {
        "candidate_role_1_code",
        "candidate_role_1_score",
        "candidate_role_2_code",
        "candidate_role_2_score",
        "seniority_rank",
        "candidate_seniority_1_code",
        "candidate_seniority_1_score",
        "candidate_seniority_2_code",
        "candidate_seniority_2_score",
    }
)


def _read_model_csv(path: Path, model: type[ModelT], label: str) -> tuple[ModelT, ...]:
    """Read one exact stable model contract with controlled row errors."""
    try:
        input_file = path.open("r", encoding="utf-8", newline="")
    except OSError as error:
        raise RelevanceInputError(f"{label} input could not be read: {path}") from error
    expected = tuple(model.model_fields)
    rows: list[ModelT] = []
    with input_file:
        reader = csv.DictReader(input_file, strict=True)
        if tuple(reader.fieldnames or ()) != expected:
            raise RelevanceInputError(f"{label} CSV headers do not match its contract")
        for row_number, source_row in enumerate(reader, start=2):
            if None in source_row:
                raise RelevanceInputError(
                    f"{label} CSV row {row_number} has more values than headers"
                )
            values: dict[str, object] = dict(source_row)
            for field_name in SEQUENCE_FIELDS & values.keys():
                try:
                    parsed = json.loads(str(values[field_name]))
                except json.JSONDecodeError as error:
                    raise RelevanceInputError(
                        f"{label} CSV row {row_number} has invalid {field_name} JSON"
                    ) from error
                if not isinstance(parsed, list):
                    raise RelevanceInputError(
                        f"{label} CSV row {row_number} has invalid {field_name}"
                    )
                values[field_name] = tuple(parsed)
            for field_name in OPTIONAL_FIELDS & values.keys():
                if values[field_name] == "":
                    values[field_name] = None
            try:
                rows.append(model.model_validate(values))
            except ValidationError as error:
                raise RelevanceInputError(
                    f"{label} CSV row {row_number} failed its typed contract"
                ) from error
    return tuple(rows)


def read_role_classifications_csv(path: Path) -> tuple[JobRoleClassification, ...]:
    """Read stable Feature 5 final role rows."""
    return _read_model_csv(path, JobRoleClassification, "role classification")


def read_seniority_classifications_csv(
    path: Path,
) -> tuple[JobSeniorityClassification, ...]:
    """Read stable Feature 6 final seniority rows for diagnostics only."""
    return _read_model_csv(path, JobSeniorityClassification, "seniority classification")


def read_job_requirement_matches_csv(path: Path) -> tuple[JobRequirementMatch, ...]:
    """Read stable Feature 3 distinct job-requirement rows."""
    return _read_model_csv(path, JobRequirementMatch, "requirement match")


def read_profile_relevance_csv(path: Path) -> tuple[JobProfileRelevance, ...]:
    """Read stable Feature 7 final profile-relevance decisions."""
    return _read_model_csv(path, JobProfileRelevance, "profile relevance")


# =============================================================================
# Stable Feature 7 output columns and writer
# =============================================================================


JOB_PROFILE_RELEVANCE_COLUMNS = tuple(JobProfileRelevance.model_fields)
PROFILE_RELEVANCE_EVIDENCE_COLUMNS = tuple(ProfileRelevanceEvidence.model_fields)
PROFILE_RELEVANCE_SUMMARY_COLUMNS = tuple(ProfileRelevanceSummary.model_fields)
PROFILE_RELEVANCE_REVIEW_COLUMNS = tuple(ProfileRelevanceReviewQueueItem.model_fields)
PROFILE_RELEVANCE_DIAGNOSTIC_COLUMNS = tuple(ProfileRelevanceDiagnostic.model_fields)


def write_profile_relevance_outputs(
    output_dir: Path, result: ProfileRelevanceRunResult
) -> dict[str, int]:
    """Write the five approved profile-relevance CSV outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "job_profile_relevance.csv": (
            result.classifications,
            JOB_PROFILE_RELEVANCE_COLUMNS,
        ),
        "profile_relevance_evidence.csv": (
            result.evidence,
            PROFILE_RELEVANCE_EVIDENCE_COLUMNS,
        ),
        "profile_relevance_summary.csv": (
            (result.summary,),
            PROFILE_RELEVANCE_SUMMARY_COLUMNS,
        ),
        "profile_relevance_review_queue.csv": (
            result.review_queue,
            PROFILE_RELEVANCE_REVIEW_COLUMNS,
        ),
        "profile_relevance_diagnostics.csv": (
            result.diagnostics,
            PROFILE_RELEVANCE_DIAGNOSTIC_COLUMNS,
        ),
    }
    return {
        filename: write_model_csv(output_dir / filename, rows, columns)
        for filename, (rows, columns) in outputs.items()
    }
