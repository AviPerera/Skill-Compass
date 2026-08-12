"""Coordinate deterministic extraction for typed cleaned-job records.

This reusable application engine composes matching and aggregation but must not
read CSV files, render graphs, persist records, or classify roles or seniority.
"""

from __future__ import annotations

from skill_compass.extraction.aggregation import (
    aggregate_job_matches,
    build_extraction_quality_metrics,
    build_skill_demand,
    job_is_eligible,
    summarize_job,
)
from skill_compass.extraction.errors import (
    ExtractionInputError,
    ExtractionReconciliationError,
)
from skill_compass.extraction.matcher import extract_job_evidence, extractor_config_hash
from skill_compass.schemas.extraction import (
    ExtractionProfile,
    ExtractionRunResult,
    RequirementDictionary,
)
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Reusable extraction orchestration
# =============================================================================


def stable_cleaned_jobs(cleaned_jobs: tuple[CleanedJob, ...]) -> tuple[CleanedJob, ...]:
    """Validate unique logical identities and return deterministic job order."""
    identities = [(job.source_code, job.source_job_id) for job in cleaned_jobs]
    if len(identities) != len(set(identities)):
        raise ExtractionInputError(
            "cleaned jobs contain duplicate source_code and source_job_id identities"
        )
    return tuple(
        sorted(
            cleaned_jobs,
            key=lambda job: (
                job.source_code,
                job.source_row_number,
                job.source_job_id,
            ),
        )
    )


def extract_requirements(
    cleaned_jobs: tuple[CleanedJob, ...],
    profile: ExtractionProfile,
    dictionary: RequirementDictionary,
) -> ExtractionRunResult:
    """Extract, aggregate, summarize, and reconcile typed cleaned jobs."""
    ordered_jobs = stable_cleaned_jobs(cleaned_jobs)
    all_evidence = []
    all_matches = []
    summaries = []
    suppressed_total = 0

    for job in ordered_jobs:
        if not job_is_eligible(job, profile):
            summaries.append(summarize_job(job, (), 0, 0, profile, dictionary))
            continue

        job_evidence = extract_job_evidence(job, profile, dictionary)
        job_matches = aggregate_job_matches(job_evidence.evidence, profile, dictionary)
        positive_evidence_count = sum(
            row.evidence_status in {"accepted", "review"}
            for row in job_evidence.evidence
        )
        summaries.append(
            summarize_job(
                job,
                job_matches,
                positive_evidence_count,
                job_evidence.suppressed_negative_context_count,
                profile,
                dictionary,
            )
        )
        all_evidence.extend(job_evidence.evidence)
        all_matches.extend(job_matches)
        suppressed_total += job_evidence.suppressed_negative_context_count

    evidence = tuple(all_evidence)
    matches = tuple(all_matches)
    job_summaries = tuple(summaries)
    eligible_count = sum(summary.analytically_eligible for summary in job_summaries)
    skipped_count = len(job_summaries) - eligible_count
    skill_demand = build_skill_demand(
        matches=matches,
        eligible_job_count=eligible_count,
        dictionary=dictionary,
        profile=profile,
    )
    quality_metrics = build_extraction_quality_metrics(
        input_cleaned_jobs=len(ordered_jobs),
        processed_jobs=eligible_count,
        skipped_jobs=skipped_count,
        processing_error_jobs=0,
        summaries=job_summaries,
        matches=matches,
        evidence=evidence,
        dictionary=dictionary,
        profile=profile,
    )
    reconciliation_passed = (
        next(
            metric.metric_value
            for metric in quality_metrics
            if metric.metric_name == "reconciliation_pass"
        )
        == "true"
    )
    evidence_reconciliation_passed = (
        next(
            metric.metric_value
            for metric in quality_metrics
            if metric.metric_name == "match_evidence_reconciliation_pass"
        )
        == "true"
    )
    if not reconciliation_passed or not evidence_reconciliation_passed:
        raise ExtractionReconciliationError(
            "extraction run or accepted evidence counts did not reconcile"
        )

    return ExtractionRunResult(
        profile=profile,
        requirement_dictionary=dictionary,
        extractor_config_hash=extractor_config_hash(profile),
        input_cleaned_jobs=len(ordered_jobs),
        analytically_eligible_jobs=eligible_count,
        analytically_ineligible_jobs=skipped_count,
        processed_jobs=eligible_count,
        skipped_jobs=skipped_count,
        processing_error_jobs=0,
        evidence=evidence,
        job_requirement_matches=matches,
        job_summaries=job_summaries,
        skill_demand=skill_demand,
        quality_metrics=quality_metrics,
        processing_errors=(),
        suppressed_negative_context_count=suppressed_total,
        reconciliation_passed=True,
    )
