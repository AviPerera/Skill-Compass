"""Aggregate evidence into job matches, demand facts, and quality metrics.

This channel-neutral extraction layer calculates deterministic summaries and
must not read or write files, render charts, or contain Power BI formatting.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal

from skill_compass.schemas.extraction import (
    ExtractionProfile,
    ExtractionQualityMetric,
    JobExtractionSummary,
    JobRequirementMatch,
    RequirementDictionary,
    RequirementEvidence,
    SkillDemandSummary,
)
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Match scoring and confidence
# =============================================================================


SECTION_ORDER = {
    "title_clean": 0,
    "summary_text_clean": 1,
    "bullet_points_clean": 2,
    "description_text_clean": 3,
}


def bounded_match_score(evidence: tuple[RequirementEvidence, ...]) -> Decimal:
    """Calculate a bounded explainable score from weight, breadth, and repetition.

    The score is not a probability. Sixty percent comes from the strongest
    section, up to fifteen percent each comes from distinct sections and extra
    occurrences, and a canonical-name alias contributes ten percent.
    """
    highest_weight = max(row.section_weight for row in evidence)
    distinct_sections = len({row.section_name for row in evidence})
    section_bonus = min(Decimal("0.15"), Decimal("0.05") * (distinct_sections - 1))
    occurrence_bonus = min(Decimal("0.15"), Decimal("0.03") * (len(evidence) - 1))
    canonical_bonus = (
        Decimal("0.10")
        if any(
            row.alias_text.casefold() == row.requirement_name.casefold()
            for row in evidence
        )
        else Decimal("0")
    )
    score = (
        highest_weight * Decimal("0.60")
        + section_bonus
        + occurrence_bonus
        + canonical_bonus
    )
    return min(Decimal("1"), score).quantize(Decimal("0.0001"))


def confidence_for_score(
    score: Decimal,
    evidence: tuple[RequirementEvidence, ...],
    profile: ExtractionProfile,
) -> str:
    """Map one deterministic score to profile-controlled confidence labels."""
    if any(row.evidence_status == "review" for row in evidence):
        return "review"
    thresholds = profile.confidence_thresholds
    if score >= thresholds.high_min:
        return "high"
    if score >= thresholds.medium_min:
        return "medium"
    if score >= thresholds.low_min:
        return "low"
    return "review"


def aggregate_job_matches(
    evidence: tuple[RequirementEvidence, ...],
    profile: ExtractionProfile,
    dictionary: RequirementDictionary,
) -> tuple[JobRequirementMatch, ...]:
    """Create one match per job and requirement from accepted/review evidence."""
    positive_evidence = tuple(
        row for row in evidence if row.evidence_status in {"accepted", "review"}
    )
    grouped: dict[tuple[str, str, str], list[RequirementEvidence]] = defaultdict(list)
    for row in positive_evidence:
        grouped[(row.source_code, row.source_job_id, row.requirement_code)].append(row)

    requirement_lookup = {
        requirement.requirement_code: requirement
        for requirement in dictionary.requirements
    }
    matches: list[JobRequirementMatch] = []
    for identity in sorted(
        grouped,
        key=lambda key: (
            key[0],
            key[1],
            requirement_lookup[key[2]].sort_order,
            key[2],
        ),
    ):
        rows = tuple(grouped[identity])
        requirement = requirement_lookup[identity[2]]
        score = bounded_match_score(rows)
        confidence = confidence_for_score(score, rows, profile)
        quality_flags = ()
        if confidence == "low":
            quality_flags = ("low_confidence_match",)
        elif confidence == "review":
            quality_flags = ("review_required",)
        matches.append(
            JobRequirementMatch(
                source_code=identity[0],
                source_job_id=identity[1],
                requirement_code=requirement.requirement_code,
                requirement_name=requirement.requirement_name,
                requirement_type=requirement.requirement_type,
                category_code=requirement.category_code,
                category_name=requirement.category_name,
                dashboard_group=requirement.dashboard_group,
                evidence_count=len(rows),
                matched_sections=tuple(
                    sorted(
                        {row.section_name for row in rows},
                        key=SECTION_ORDER.__getitem__,
                    )
                ),
                matched_aliases=tuple(
                    sorted(
                        {row.alias_text for row in rows},
                        key=lambda value: (value.casefold(), value),
                    )
                ),
                highest_section_weight=max(row.section_weight for row in rows),
                extraction_score=score,
                confidence_level=confidence,
                extraction_method="deterministic_dictionary",
                dictionary_version=dictionary.dictionary_version,
                dictionary_hash=dictionary.dictionary_hash,
                extractor_version=profile.extractor_version,
                profile_version=profile.profile_version,
                extraction_output_schema_version=(
                    profile.extraction_output_schema_version
                ),
                quality_flags=quality_flags,
            )
        )
    return tuple(matches)


# =============================================================================
# Job and demand summaries
# =============================================================================


def job_is_eligible(job: CleanedJob, profile: ExtractionProfile) -> bool:
    """Apply the profile's minimum eligibility gate to one cleaned job."""
    rules = profile.minimum_analytical_eligibility
    if rules.require_analytically_eligible and not job.analytically_eligible:
        return False
    if rules.require_usable_description and job.usable_description_status != "usable":
        return False
    return True


def summarize_job(
    job: CleanedJob,
    matches: tuple[JobRequirementMatch, ...],
    positive_evidence_count: int,
    suppressed_evidence_count: int,
    profile: ExtractionProfile,
    dictionary: RequirementDictionary,
) -> JobExtractionSummary:
    """Create one stable per-job status and count record."""
    eligible = job_is_eligible(job, profile)
    if not eligible:
        return JobExtractionSummary(
            source_code=job.source_code,
            source_job_id=job.source_job_id,
            analytically_eligible=False,
            extraction_status="skipped_ineligible",
            distinct_requirement_count=0,
            distinct_skill_count=0,
            evidence_count=0,
            high_confidence_count=0,
            medium_confidence_count=0,
            low_confidence_count=0,
            review_count=0,
            category_count=0,
            extraction_quality_flags=("analytically_ineligible",),
            dictionary_version=dictionary.dictionary_version,
            extractor_version=profile.extractor_version,
        )

    confidence_counts = Counter(match.confidence_level for match in matches)
    flags: list[str] = []
    if suppressed_evidence_count:
        flags.append("negative_context_suppressed")
    if confidence_counts["low"]:
        flags.append("low_confidence_matches")
    if confidence_counts["review"]:
        flags.append("review_required")

    if confidence_counts["review"]:
        status = "review_required"
    elif matches:
        status = "extracted"
    else:
        status = "no_requirements_detected"
    return JobExtractionSummary(
        source_code=job.source_code,
        source_job_id=job.source_job_id,
        analytically_eligible=True,
        extraction_status=status,
        distinct_requirement_count=len(matches),
        distinct_skill_count=sum(
            match.requirement_type == "skill" for match in matches
        ),
        evidence_count=positive_evidence_count,
        high_confidence_count=confidence_counts["high"],
        medium_confidence_count=confidence_counts["medium"],
        low_confidence_count=confidence_counts["low"],
        review_count=confidence_counts["review"],
        category_count=len({match.category_code for match in matches}),
        extraction_quality_flags=tuple(flags),
        dictionary_version=dictionary.dictionary_version,
        extractor_version=profile.extractor_version,
    )


def build_skill_demand(
    *,
    matches: tuple[JobRequirementMatch, ...],
    eligible_job_count: int,
    dictionary: RequirementDictionary,
    profile: ExtractionProfile,
) -> tuple[SkillDemandSummary, ...]:
    """Calculate distinct eligible-job demand for every active skill requirement."""
    matches_by_requirement: dict[str, list[JobRequirementMatch]] = defaultdict(list)
    for match in matches:
        if match.requirement_type == "skill":
            matches_by_requirement[match.requirement_code].append(match)

    provisional: list[tuple[object, ...]] = []
    for requirement in dictionary.requirements:
        if requirement.requirement_type != "skill":
            continue
        requirement_matches = tuple(
            matches_by_requirement[requirement.requirement_code]
        )
        matched_job_count = len(
            {(match.source_code, match.source_job_id) for match in requirement_matches}
        )
        demand_rate = (
            Decimal(matched_job_count) / Decimal(eligible_job_count)
            if eligible_job_count
            else Decimal("0")
        ).quantize(Decimal("0.000001"))
        confidence_counts = Counter(
            match.confidence_level for match in requirement_matches
        )
        provisional.append(
            (
                requirement,
                matched_job_count,
                demand_rate,
                sum(match.evidence_count for match in requirement_matches),
                confidence_counts,
            )
        )

    ranked = sorted(
        provisional,
        key=lambda item: (
            -int(item[1]),
            -int(item[3]),
            item[0].sort_order,
            item[0].requirement_code,
        ),
    )
    return tuple(
        SkillDemandSummary(
            requirement_code=requirement.requirement_code,
            requirement_name=requirement.requirement_name,
            category_code=requirement.category_code,
            category_name=requirement.category_name,
            dashboard_group=requirement.dashboard_group,
            eligible_job_count=eligible_job_count,
            matched_job_count=matched_job_count,
            demand_rate=demand_rate,
            total_evidence_count=evidence_count,
            high_confidence_job_count=confidence_counts["high"],
            medium_confidence_job_count=confidence_counts["medium"],
            low_confidence_job_count=confidence_counts["low"],
            review_job_count=confidence_counts["review"],
            rank_overall=rank,
            dictionary_version=dictionary.dictionary_version,
            extractor_version=profile.extractor_version,
            extraction_output_schema_version=(profile.extraction_output_schema_version),
        )
        for rank, (
            requirement,
            matched_job_count,
            demand_rate,
            evidence_count,
            confidence_counts,
        ) in enumerate(ranked, start=1)
    )


# =============================================================================
# Stable extraction quality metrics
# =============================================================================


def metric(
    category: str,
    name: str,
    value: object,
    status: str,
    detail: str,
) -> ExtractionQualityMetric:
    """Create one stable string-valued extraction quality metric."""
    if isinstance(value, bool):
        serialized = str(value).lower()
    elif isinstance(value, Decimal):
        serialized = format(value, "f")
    else:
        serialized = str(value)
    return ExtractionQualityMetric(
        metric_category=category,
        metric_name=name,
        metric_value=serialized,
        metric_status=status,
        metric_detail=detail,
    )


def median_count(values: tuple[int, ...]) -> Decimal:
    """Calculate an exact Decimal median without binary floating-point values."""
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return Decimal(ordered[midpoint])
    return Decimal(ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def build_extraction_quality_metrics(
    *,
    input_cleaned_jobs: int,
    processed_jobs: int,
    skipped_jobs: int,
    processing_error_jobs: int,
    summaries: tuple[JobExtractionSummary, ...],
    matches: tuple[JobRequirementMatch, ...],
    evidence: tuple[RequirementEvidence, ...],
    dictionary: RequirementDictionary,
    profile: ExtractionProfile,
) -> tuple[ExtractionQualityMetric, ...]:
    """Build reconciliation, coverage, confidence, dictionary, and evidence metrics."""
    reconciliation = (
        input_cleaned_jobs == processed_jobs + skipped_jobs + processing_error_jobs
    )
    eligible_summaries = tuple(
        summary for summary in summaries if summary.analytically_eligible
    )
    requirement_counts = tuple(
        summary.distinct_requirement_count for summary in eligible_summaries
    )
    average = (
        Decimal(sum(requirement_counts)) / Decimal(len(requirement_counts))
        if requirement_counts
        else Decimal("0")
    ).quantize(Decimal("0.0001"))
    median = median_count(requirement_counts).quantize(Decimal("0.0001"))
    confidence_counts = Counter(match.confidence_level for match in matches)
    accepted_evidence = tuple(
        row for row in evidence if row.evidence_status in {"accepted", "review"}
    )
    evidence_reconciliation = sum(match.evidence_count for match in matches) == len(
        accepted_evidence
    )
    section_counts = Counter(row.section_name for row in accepted_evidence)
    suppressed_count = sum(
        row.evidence_status == "suppressed_negative_context" for row in evidence
    )

    metrics = [
        metric(
            "run_reconciliation",
            "input_cleaned_jobs",
            input_cleaned_jobs,
            "info",
            "Typed cleaned jobs supplied to extraction.",
        ),
        metric(
            "run_reconciliation",
            "analytically_eligible_jobs",
            len(eligible_summaries),
            "info",
            "Jobs included in the skill-demand denominator.",
        ),
        metric(
            "run_reconciliation",
            "analytically_ineligible_jobs",
            skipped_jobs,
            "info",
            "Cleaned jobs excluded by the profile eligibility gate.",
        ),
        metric(
            "run_reconciliation",
            "processed_jobs",
            processed_jobs,
            "info",
            "Eligible jobs processed successfully.",
        ),
        metric(
            "run_reconciliation",
            "skipped_jobs",
            skipped_jobs,
            "info",
            "Ineligible jobs skipped before matching.",
        ),
        metric(
            "run_reconciliation",
            "processing_error_jobs",
            processing_error_jobs,
            "info",
            "Jobs with controlled processing errors.",
        ),
        metric(
            "run_reconciliation",
            "reconciliation_pass",
            reconciliation,
            "pass" if reconciliation else "fail",
            "input_cleaned_jobs = processed_jobs + skipped_jobs + processing_error_jobs",
        ),
        metric(
            "run_reconciliation",
            "match_evidence_reconciliation_pass",
            evidence_reconciliation,
            "pass" if evidence_reconciliation else "fail",
            "Accepted evidence rows equal summed job-match evidence counts.",
        ),
        metric(
            "extraction_coverage",
            "jobs_with_at_least_one_requirement",
            sum(
                summary.distinct_requirement_count > 0 for summary in eligible_summaries
            ),
            "info",
            "Eligible jobs with at least one canonical requirement.",
        ),
        metric(
            "extraction_coverage",
            "jobs_with_no_requirements",
            sum(
                summary.distinct_requirement_count == 0
                for summary in eligible_summaries
            ),
            "info",
            "Eligible jobs with no detected requirement.",
        ),
        metric(
            "extraction_coverage",
            "jobs_requiring_review",
            sum(
                summary.extraction_status == "review_required"
                for summary in eligible_summaries
            ),
            "info",
            "Eligible jobs containing review-level matches.",
        ),
        metric(
            "extraction_coverage",
            "total_job_requirement_matches",
            len(matches),
            "info",
            "Distinct job and requirement rows.",
        ),
        metric(
            "extraction_coverage",
            "total_evidence_rows",
            len(evidence),
            "info",
            "Accepted and explicitly suppressed evidence rows.",
        ),
        metric(
            "extraction_coverage",
            "average_requirements_per_eligible_job",
            average,
            "info",
            "Mean distinct requirements across eligible jobs including zero-match jobs.",
        ),
        metric(
            "extraction_coverage",
            "median_requirements_per_eligible_job",
            median,
            "info",
            "Median distinct requirements across eligible jobs including zero-match jobs.",
        ),
        metric(
            "extraction_coverage",
            "minimum_requirements_per_eligible_job",
            min(requirement_counts, default=0),
            "info",
            "Minimum distinct requirements for an eligible job.",
        ),
        metric(
            "extraction_coverage",
            "maximum_requirements_per_eligible_job",
            max(requirement_counts, default=0),
            "info",
            "Maximum distinct requirements for an eligible job.",
        ),
        metric(
            "confidence",
            "high_confidence_matches",
            confidence_counts["high"],
            "info",
            "Distinct high-confidence job-requirement matches.",
        ),
        metric(
            "confidence",
            "medium_confidence_matches",
            confidence_counts["medium"],
            "info",
            "Distinct medium-confidence job-requirement matches.",
        ),
        metric(
            "confidence",
            "low_confidence_matches",
            confidence_counts["low"],
            "info",
            "Distinct low-confidence job-requirement matches.",
        ),
        metric(
            "confidence",
            "review_matches",
            confidence_counts["review"],
            "warning" if confidence_counts["review"] else "info",
            "Distinct job-requirement matches requiring review.",
        ),
        metric(
            "dictionary",
            "active_requirements",
            len(dictionary.requirements),
            "info",
            "Validated active canonical requirements.",
        ),
        metric(
            "dictionary",
            "active_aliases",
            len(dictionary.active_aliases),
            "info",
            "Validated active literal aliases.",
        ),
        metric(
            "dictionary",
            "duplicate_alias_conflicts",
            0,
            "pass",
            "Dictionary loading rejects duplicate and conflicting active aliases.",
        ),
        metric(
            "dictionary",
            "dictionary_hash_present",
            bool(dictionary.dictionary_hash),
            "pass" if dictionary.dictionary_hash else "fail",
            "Canonical SHA-256 dictionary hash is present.",
        ),
        metric(
            "dictionary",
            "profile_hash_present",
            bool(profile.profile_hash),
            "pass" if profile.profile_hash else "fail",
            "Canonical SHA-256 profile hash is present.",
        ),
        metric(
            "evidence_quality",
            "title_evidence_count",
            section_counts["title_clean"],
            "info",
            "Accepted title evidence rows.",
        ),
        metric(
            "evidence_quality",
            "summary_evidence_count",
            section_counts["summary_text_clean"],
            "info",
            "Accepted summary evidence rows.",
        ),
        metric(
            "evidence_quality",
            "bullet_evidence_count",
            section_counts["bullet_points_clean"],
            "info",
            "Accepted bullet evidence rows.",
        ),
        metric(
            "evidence_quality",
            "description_evidence_count",
            section_counts["description_text_clean"],
            "info",
            "Accepted description evidence rows.",
        ),
        metric(
            "evidence_quality",
            "suppressed_negative_context_count",
            suppressed_count,
            "info",
            "Alias occurrences excluded by conservative negative-context controls.",
        ),
        metric(
            "evidence_quality",
            "records_with_extraction_quality_flags",
            sum(bool(summary.extraction_quality_flags) for summary in summaries),
            "info",
            "Job summaries carrying explicit extraction quality flags.",
        ),
    ]
    return tuple(metrics)
