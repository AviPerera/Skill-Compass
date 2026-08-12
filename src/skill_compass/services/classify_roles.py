"""Orchestrate cleaned-CSV role classification and stable output writing.

This application service coordinates existing adapters and the reusable role
engine; it must not implement rules, render charts, or invoke external APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skill_compass.adapters.classification_csv import (
    write_role_classification_outputs,
)
from skill_compass.adapters.extraction_csv import read_cleaned_jobs_csv
from skill_compass.classification.config import load_role_rules
from skill_compass.classification.errors import RoleInputError
from skill_compass.classification.roles import classify_roles
from skill_compass.extraction.errors import ExtractionInputError
from skill_compass.schemas.classification import RoleClassificationRunResult
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Typed file-boundary result
# =============================================================================


@dataclass(frozen=True, slots=True)
class RoleOutputFileSummary:
    """Describe one generated role CSV and its data-row count."""

    path: Path
    row_count: int


@dataclass(frozen=True, slots=True)
class RoleClassificationCsvRunResult:
    """Return typed role results plus generated file evidence."""

    input_path: Path
    rules_path: Path
    output_dir: Path
    cleaned_jobs: tuple[CleanedJob, ...]
    classification: RoleClassificationRunResult
    output_files: tuple[RoleOutputFileSummary, ...]


def process_role_classification(
    *, input_path: Path, rules_path: Path, output_dir: Path
) -> RoleClassificationCsvRunResult:
    """Load canonical jobs and rules, classify, reconcile, and write CSVs."""
    if not input_path.is_file():
        raise RoleInputError(f"cleaned Feature 2 input is missing: {input_path}")
    try:
        cleaned_jobs = read_cleaned_jobs_csv(input_path)
    except ExtractionInputError as error:
        raise RoleInputError(str(error)) from error
    rules = load_role_rules(rules_path)
    result = classify_roles(cleaned_jobs, rules)
    output_counts = write_role_classification_outputs(output_dir, result)
    return RoleClassificationCsvRunResult(
        input_path=input_path,
        rules_path=rules_path,
        output_dir=output_dir,
        cleaned_jobs=cleaned_jobs,
        classification=result,
        output_files=tuple(
            RoleOutputFileSummary(output_dir / filename, row_count)
            for filename, row_count in output_counts.items()
        ),
    )
