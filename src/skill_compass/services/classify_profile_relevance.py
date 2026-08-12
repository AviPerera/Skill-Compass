"""Orchestrate canonical profile-relevance classification and CSV outputs.

This application service joins existing Feature 2/3/5/6 results and calls the
reusable classifier. It must not implement rules, render charts, or call APIs.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from skill_compass.adapters.extraction_csv import read_cleaned_jobs_csv
from skill_compass.adapters.relevance_csv import (
    read_job_requirement_matches_csv,
    read_role_classifications_csv,
    read_seniority_classifications_csv,
    write_profile_relevance_outputs,
)
from skill_compass.classification.errors import RelevanceInputError
from skill_compass.classification.relevance import (
    RelevanceJobInput,
    classify_profile_relevance,
)
from skill_compass.classification.relevance_config import load_relevance_rules
from skill_compass.extraction.errors import ExtractionInputError
from skill_compass.schemas.classification import ProfileRelevanceRunResult
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Conventional local input paths and typed service result
# =============================================================================


CLEANED_JOBS_FILENAME = "cleaned_jobs.csv"
ROLE_CLASSIFICATIONS_PATH = Path("role_classification/job_role_classifications.csv")
SENIORITY_CLASSIFICATIONS_PATH = Path(
    "seniority_classification/job_seniority_classifications.csv"
)
REQUIREMENT_MATCHES_PATH = Path("skill_extraction/job_requirement_matches.csv")


@dataclass(frozen=True, slots=True)
class RelevanceOutputFileSummary:
    """Describe one generated relevance CSV and its data-row count."""

    path: Path
    row_count: int


@dataclass(frozen=True, slots=True)
class ProfileRelevanceCsvRunResult:
    """Return joined canonical jobs, results, and generated-file evidence."""

    input_dir: Path
    rules_path: Path
    output_dir: Path
    cleaned_jobs: tuple[CleanedJob, ...]
    classification: ProfileRelevanceRunResult
    output_files: tuple[RelevanceOutputFileSummary, ...]


def _unique_by_job(
    rows: tuple[object, ...], label: str
) -> dict[tuple[str, str], object]:
    """Index one-row-per-job upstream records and reject duplicate identities."""
    indexed: dict[tuple[str, str], object] = {}
    for row in rows:
        key = (str(getattr(row, "source_code")), str(getattr(row, "source_job_id")))
        if key in indexed:
            raise RelevanceInputError(f"duplicate {label} row for {key[0]}:{key[1]}")
        indexed[key] = row
    return indexed


def _join_inputs(
    input_dir: Path,
) -> tuple[tuple[CleanedJob, ...], tuple[RelevanceJobInput, ...]]:
    """Read conventional outputs and perform an exact canonical identity join."""
    try:
        jobs = read_cleaned_jobs_csv(input_dir / CLEANED_JOBS_FILENAME)
    except ExtractionInputError as error:
        raise RelevanceInputError(str(error)) from error
    roles = _unique_by_job(
        read_role_classifications_csv(input_dir / ROLE_CLASSIFICATIONS_PATH), "role"
    )
    seniority_path = input_dir / SENIORITY_CLASSIFICATIONS_PATH
    seniorities = (
        _unique_by_job(read_seniority_classifications_csv(seniority_path), "seniority")
        if seniority_path.is_file()
        else {}
    )
    requirements_by_job: dict[tuple[str, str], list[object]] = defaultdict(list)
    for requirement in read_job_requirement_matches_csv(
        input_dir / REQUIREMENT_MATCHES_PATH
    ):
        requirements_by_job[
            (requirement.source_code, requirement.source_job_id)
        ].append(requirement)

    job_keys = {(job.source_code, job.source_job_id) for job in jobs}
    if set(roles) != job_keys:
        missing = len(job_keys - set(roles))
        extra = len(set(roles) - job_keys)
        raise RelevanceInputError(
            f"role input does not reconcile to cleaned jobs: {missing} missing, {extra} extra"
        )
    unknown_requirement_keys = set(requirements_by_job) - job_keys
    if unknown_requirement_keys:
        raise RelevanceInputError(
            "requirement input contains jobs absent from the cleaned-job contract"
        )
    if set(seniorities) - job_keys:
        raise RelevanceInputError(
            "seniority input contains jobs absent from the cleaned-job contract"
        )

    joined = tuple(
        RelevanceJobInput(
            job=job,
            role=roles[(job.source_code, job.source_job_id)],
            requirements=tuple(
                sorted(
                    requirements_by_job[(job.source_code, job.source_job_id)],
                    key=lambda row: row.requirement_code,
                )
            ),
            seniority=seniorities.get((job.source_code, job.source_job_id)),
        )
        for job in jobs
    )
    return jobs, joined


# =============================================================================
# Public service boundary
# =============================================================================


def process_profile_relevance(
    *,
    input_dir: Path,
    rules_path: Path,
    output_dir: Path,
    classified_at: datetime | None = None,
) -> ProfileRelevanceCsvRunResult:
    """Join upstream outputs, classify every job, reconcile, and write CSVs."""
    jobs, inputs = _join_inputs(input_dir)
    rules = load_relevance_rules(rules_path)
    run_timestamp = classified_at or datetime.now(UTC)
    if run_timestamp.tzinfo is None:
        raise RelevanceInputError("classified_at must be timezone-aware")
    result = classify_profile_relevance(
        inputs, rules, classified_at=run_timestamp.astimezone(UTC)
    )
    output_counts = write_profile_relevance_outputs(output_dir, result)
    return ProfileRelevanceCsvRunResult(
        input_dir=input_dir,
        rules_path=rules_path,
        output_dir=output_dir,
        cleaned_jobs=jobs,
        classification=result,
        output_files=tuple(
            RelevanceOutputFileSummary(output_dir / filename, row_count)
            for filename, row_count in output_counts.items()
        ),
    )
