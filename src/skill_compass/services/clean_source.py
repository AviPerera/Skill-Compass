"""Orchestrate format-neutral canonical mapping and deterministic cleaning.

This application service belongs between file adapters and reusable processing
logic. It coordinates mapping, deduplication, cleaning, quality metrics, and
approved outputs; it must not parse source files or implement business rules.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from skill_compass.adapters.csv import write_pipeline_outputs
from skill_compass.cleaning.service import clean_mapped_job
from skill_compass.mapping.config import SourceMappingConfig
from skill_compass.mapping.deduplication import deduplicate_mapped_jobs
from skill_compass.mapping.service import map_source_row
from skill_compass.quality.service import build_quality_metrics
from skill_compass.schemas.jobs import CleanedJob, MappedJob, RejectedRecord
from skill_compass.schemas.quality import QualityMetric

# =============================================================================
# Input and result contracts
# =============================================================================


class SourceRow(Protocol):
    """Describe the format-neutral row contract supplied by file adapters."""

    source_row_number: int
    values: Mapping[str, str]


class ReconciliationError(RuntimeError):
    """Report a fatal failure to reconcile input, cleaned, and rejected rows."""


@dataclass(frozen=True, slots=True)
class OutputFileSummary:
    """Describe one generated output file and its data-row count."""

    path: Path
    row_count: int


@dataclass(frozen=True, slots=True)
class CleaningRunResult:
    """Return typed records, counts, configuration, and generated output evidence."""

    input_path: Path
    output_dir: Path
    input_encoding: str
    source_column_count: int
    input_rows: int
    mapping_config: SourceMappingConfig
    mapping_success_rows: int
    structurally_rejected_rows: int
    duplicate_identity_count: int
    duplicate_same_content_rows: int
    duplicate_conflicting_content_rows: int
    mapped_jobs: tuple[MappedJob, ...]
    cleaned_jobs: tuple[CleanedJob, ...]
    rejected_records: tuple[RejectedRecord, ...]
    quality_metrics: tuple[QualityMetric, ...]
    preferred_field_use_count: int
    fallback_field_use_count: int
    analytically_eligible_rows: int
    analytically_ineligible_rows: int
    reconciliation_passed: bool
    output_files: tuple[OutputFileSummary, ...]

    @property
    def total_rejected_rows(self) -> int:
        """Return the total structural and duplicate rejected-row count."""
        return len(self.rejected_records)


# =============================================================================
# Format-neutral processing orchestration
# =============================================================================


def metric_value(metrics: tuple[QualityMetric, ...], name: str) -> str:
    """Return one unique metric value from a typed quality metric collection."""
    return next(metric.metric_value for metric in metrics if metric.metric_name == name)


def process_source_rows(
    *,
    input_path: Path,
    output_dir: Path,
    input_encoding: str,
    source_column_count: int,
    source_rows: tuple[SourceRow, ...],
    mapping_config: SourceMappingConfig,
) -> CleaningRunResult:
    """Map and clean rows already parsed by an approved outer adapter."""
    outcomes = tuple(
        map_source_row(
            source_row.values,
            mapping_config,
            source_row.source_row_number,
        )
        for source_row in source_rows
    )

    valid_mapped_jobs = tuple(
        outcome.mapped_job for outcome in outcomes if outcome.mapped_job is not None
    )
    structural_rejections = tuple(
        outcome.rejected_record
        for outcome in outcomes
        if outcome.rejected_record is not None
    )
    deduplication = deduplicate_mapped_jobs(valid_mapped_jobs)
    cleaned_jobs = tuple(clean_mapped_job(job) for job in deduplication.survivors)
    rejected_records = tuple(
        sorted(
            (*structural_rejections, *deduplication.rejections),
            key=lambda rejection: rejection.source_row_number,
        )
    )
    quality_metrics = build_quality_metrics(
        input_rows=len(source_rows),
        mapping_outcomes=outcomes,
        deduplication=deduplication,
        cleaned_jobs=cleaned_jobs,
    )
    reconciliation_passed = (
        metric_value(quality_metrics, "reconciliation_pass") == "true"
    )
    if not reconciliation_passed:
        raise ReconciliationError(
            "input rows do not reconcile to cleaned rows plus rejected rows"
        )

    output_counts = write_pipeline_outputs(
        output_dir=output_dir,
        mapped_jobs=deduplication.survivors,
        cleaned_jobs=cleaned_jobs,
        rejected_records=rejected_records,
        quality_metrics=quality_metrics,
    )
    output_files = tuple(
        OutputFileSummary(output_dir / filename, row_count)
        for filename, row_count in output_counts.items()
    )
    preferred_field_use_count = sum(
        len(outcome.preferred_fields_used) for outcome in outcomes
    )
    fallback_field_use_count = sum(
        len(job.fallback_fields_used) for job in valid_mapped_jobs
    )

    return CleaningRunResult(
        input_path=input_path,
        output_dir=output_dir,
        input_encoding=input_encoding,
        source_column_count=source_column_count,
        input_rows=len(source_rows),
        mapping_config=mapping_config,
        mapping_success_rows=len(valid_mapped_jobs),
        structurally_rejected_rows=len(structural_rejections),
        duplicate_identity_count=deduplication.duplicate_identity_count,
        duplicate_same_content_rows=deduplication.duplicate_same_content_rows,
        duplicate_conflicting_content_rows=(
            deduplication.duplicate_conflicting_content_rows
        ),
        mapped_jobs=deduplication.survivors,
        cleaned_jobs=cleaned_jobs,
        rejected_records=rejected_records,
        quality_metrics=quality_metrics,
        preferred_field_use_count=preferred_field_use_count,
        fallback_field_use_count=fallback_field_use_count,
        analytically_eligible_rows=sum(
            job.analytically_eligible for job in cleaned_jobs
        ),
        analytically_ineligible_rows=sum(
            not job.analytically_eligible for job in cleaned_jobs
        ),
        reconciliation_passed=True,
        output_files=output_files,
    )
