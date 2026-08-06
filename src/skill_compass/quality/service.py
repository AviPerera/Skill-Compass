"""Calculate deterministic mapping, cleaning, and reconciliation metrics.

This quality layer consumes typed pipeline results and must not perform source
mapping, record cleaning, file I/O, or database publication.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from skill_compass.mapping.deduplication import DeduplicationResult
from skill_compass.mapping.service import MappingOutcome
from skill_compass.schemas.jobs import CleanedJob
from skill_compass.schemas.quality import QualityMetric

# =============================================================================
# Stable quality metric construction
# =============================================================================


def metric(
    category: str,
    name: str,
    value: int | bool,
    status: str,
    detail: str,
) -> QualityMetric:
    """Create one typed tabular metric using stable string serialization."""
    serialized_value = str(value).lower() if isinstance(value, bool) else str(value)
    return QualityMetric(
        metric_category=category,
        metric_name=name,
        metric_value=serialized_value,
        metric_status=status,
        metric_detail=detail,
    )


def count_where(
    cleaned_jobs: tuple[CleanedJob, ...], predicate: Callable[[CleanedJob], bool]
) -> int:
    """Count cleaned jobs matching a typed callable predicate."""
    return sum(1 for job in cleaned_jobs if predicate(job))


def build_quality_metrics(
    *,
    input_rows: int,
    mapping_outcomes: tuple[MappingOutcome, ...],
    deduplication: DeduplicationResult,
    cleaned_jobs: tuple[CleanedJob, ...],
) -> tuple[QualityMetric, ...]:
    """Build stable metrics and prove input equals cleaned plus rejected rows."""
    mapped_jobs = tuple(
        outcome.mapped_job
        for outcome in mapping_outcomes
        if outcome.mapped_job is not None
    )
    structural_rejections = sum(
        outcome.rejected_record is not None for outcome in mapping_outcomes
    )
    total_rejected = structural_rejections + len(deduplication.rejections)
    reconciliation_passed = input_rows == len(cleaned_jobs) + total_rejected

    preferred_usage = Counter(
        field for outcome in mapping_outcomes for field in outcome.preferred_fields_used
    )
    fallback_usage = Counter(
        fallback.split(":", maxsplit=1)[0]
        for job in mapped_jobs
        for fallback in job.fallback_fields_used
    )

    metrics: list[QualityMetric] = [
        metric(
            "run_reconciliation",
            "input_rows",
            input_rows,
            "info",
            "Logical CSV data rows.",
        ),
        metric(
            "run_reconciliation",
            "mapping_success_rows",
            len(mapped_jobs),
            "info",
            "Structurally valid mapped rows before deduplication.",
        ),
        metric(
            "run_reconciliation",
            "structurally_rejected_rows",
            structural_rejections,
            "info",
            "Rows rejected during canonical mapping.",
        ),
        metric(
            "run_reconciliation",
            "duplicate_same_content_rows",
            deduplication.duplicate_same_content_rows,
            "info",
            "Later duplicate rows with identical process-relevant content.",
        ),
        metric(
            "run_reconciliation",
            "duplicate_conflicting_content_rows",
            deduplication.duplicate_conflicting_content_rows,
            "info",
            "Later duplicate rows with conflicting process-relevant content.",
        ),
        metric(
            "run_reconciliation",
            "cleaned_rows",
            len(cleaned_jobs),
            "info",
            "Deduplicated rows published to cleaned output.",
        ),
        metric(
            "run_reconciliation",
            "total_rejected_rows",
            total_rejected,
            "info",
            "Structural and duplicate rejections counted exactly once.",
        ),
        metric(
            "run_reconciliation",
            "reconciliation_pass",
            reconciliation_passed,
            "pass" if reconciliation_passed else "fail",
            "input_rows = cleaned_rows + total_rejected_rows",
        ),
        metric(
            "mapping_quality",
            "missing_company",
            count_where(cleaned_jobs, lambda job: job.company_name_clean is None),
            "info",
            "Cleaned survivors without a mapped company name.",
        ),
        metric(
            "mapping_quality",
            "missing_usable_description",
            count_where(
                cleaned_jobs, lambda job: job.usable_description_status == "missing"
            ),
            "info",
            "Cleaned survivors without usable description evidence.",
        ),
        metric(
            "mapping_quality",
            "analytically_eligible",
            count_where(cleaned_jobs, lambda job: job.analytically_eligible),
            "info",
            "Cleaned survivors marked analytically eligible.",
        ),
        metric(
            "mapping_quality",
            "analytically_ineligible",
            count_where(cleaned_jobs, lambda job: not job.analytically_eligible),
            "info",
            "Cleaned survivors retained but analytically ineligible.",
        ),
    ]

    for field_name, count in sorted(preferred_usage.items()):
        metrics.append(
            metric(
                "mapping_quality",
                f"preferred_field_use.{field_name}",
                count,
                "info",
                "Rows using a preferred source field for this canonical field.",
            )
        )
    for field_name, count in sorted(fallback_usage.items()):
        metrics.append(
            metric(
                "mapping_quality",
                f"fallback_field_use.{field_name}",
                count,
                "info",
                "Rows using a fallback source field for this canonical field.",
            )
        )

    cleaning_counts = {
        "salary_parsed_structured": count_where(
            cleaned_jobs, lambda job: job.salary_parse_method == "structured"
        ),
        "salary_parsed_label_fallback": count_where(
            cleaned_jobs, lambda job: job.salary_parse_method == "label_fallback"
        ),
        "salary_unknown": count_where(
            cleaned_jobs, lambda job: job.salary_parse_status == "unknown"
        ),
        "geography_parsed": count_where(
            cleaned_jobs, lambda job: job.geography_parse_status == "parsed"
        ),
        "geography_unknown": count_where(
            cleaned_jobs, lambda job: job.geography_parse_status != "parsed"
        ),
        "listing_date_parsed": count_where(
            cleaned_jobs, lambda job: job.listing_date_parse_status == "parsed"
        ),
        "listing_date_unparseable": count_where(
            cleaned_jobs, lambda job: job.listing_date_parse_status == "unparseable"
        ),
        "employment_type_known": count_where(
            cleaned_jobs, lambda job: job.employment_parse_status == "known"
        ),
        "employment_type_unknown": count_where(
            cleaned_jobs, lambda job: job.employment_parse_status != "known"
        ),
        "work_mode_structured": count_where(
            cleaned_jobs, lambda job: job.work_mode_parse_method == "structured"
        ),
        "work_mode_inferred": 0,
        "work_mode_unknown": count_where(
            cleaned_jobs, lambda job: job.work_mode_code == "unknown"
        ),
        "records_with_quality_flags": count_where(
            cleaned_jobs, lambda job: bool(job.quality_flags)
        ),
        "titles_cleaned": len(cleaned_jobs),
        "html_descriptions_converted": sum(
            bool(job.description_html_raw) and not bool(job.description_text_raw)
            for job in deduplication.survivors
        ),
        "content_hashes_produced": sum(bool(job.content_hash) for job in cleaned_jobs),
    }
    metrics.extend(
        metric(
            "cleaning_quality",
            name,
            value,
            "info",
            "Deterministic cleaning result count.",
        )
        for name, value in cleaning_counts.items()
    )
    return tuple(metrics)
