"""Orchestrate cleaned-CSV seniority classification and output writing.

This application service coordinates existing adapters and the reusable
seniority engine; it must not implement rules, render charts, or call APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skill_compass.adapters.extraction_csv import read_cleaned_jobs_csv
from skill_compass.adapters.seniority_classification_csv import (
    write_seniority_classification_outputs,
)
from skill_compass.classification.errors import SeniorityInputError
from skill_compass.classification.seniority import classify_seniority
from skill_compass.classification.seniority_config import load_seniority_rules
from skill_compass.extraction.errors import ExtractionInputError
from skill_compass.schemas.classification import SeniorityClassificationRunResult
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Typed file-boundary result
# =============================================================================


@dataclass(frozen=True, slots=True)
class SeniorityOutputFileSummary:
    """Describe one generated seniority CSV and its data-row count."""

    path: Path
    row_count: int


@dataclass(frozen=True, slots=True)
class SeniorityClassificationCsvRunResult:
    """Return typed seniority results plus generated file evidence."""

    input_path: Path
    rules_path: Path
    output_dir: Path
    cleaned_jobs: tuple[CleanedJob, ...]
    classification: SeniorityClassificationRunResult
    output_files: tuple[SeniorityOutputFileSummary, ...]


def process_seniority_classification(
    *, input_path: Path, rules_path: Path, output_dir: Path
) -> SeniorityClassificationCsvRunResult:
    """Load canonical jobs and rules, classify, reconcile, and write CSVs."""
    if not input_path.is_file():
        raise SeniorityInputError(f"cleaned Feature 2 input is missing: {input_path}")
    try:
        cleaned_jobs = read_cleaned_jobs_csv(input_path)
    except ExtractionInputError as error:
        raise SeniorityInputError(str(error)) from error
    rules = load_seniority_rules(rules_path)
    result = classify_seniority(cleaned_jobs, rules)
    output_counts = write_seniority_classification_outputs(output_dir, result)
    return SeniorityClassificationCsvRunResult(
        input_path=input_path,
        rules_path=rules_path,
        output_dir=output_dir,
        cleaned_jobs=cleaned_jobs,
        classification=result,
        output_files=tuple(
            SeniorityOutputFileSummary(output_dir / filename, row_count)
            for filename, row_count in output_counts.items()
        ),
    )
