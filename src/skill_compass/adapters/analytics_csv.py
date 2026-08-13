"""Write stable channel-neutral analytics CSV and JSON outputs.

This outer adapter serializes typed Feature 8 results only. It must not join
upstream data, calculate measures, render graphs, or create Power BI contracts.
"""

from __future__ import annotations

import json
from pathlib import Path

from skill_compass.adapters.csv import write_model_csv
from skill_compass.schemas.analytics import AnalyticsRunResult

# =============================================================================
# Stable output contracts
# =============================================================================


ANALYTICS_OUTPUTS = {
    "job_facts.csv": "job_facts",
    "job_skill_facts.csv": "job_skill_facts",
    "skill_demand.csv": "skill_demand",
    "skill_role_demand.csv": "skill_role_demand",
    "role_summary.csv": "role_summary",
    "role_seniority_summary.csv": "role_seniority",
    "seniority_summary.csv": "seniority_distribution",
    "state_summary.csv": "state_distribution",
    "city_summary.csv": "city_distribution",
    "employment_type_summary.csv": "employment_type_distribution",
    "work_mode_summary.csv": "work_mode_distribution",
    "skill_combinations.csv": "skill_combinations",
    "analytics_quality_summary.csv": "quality_metrics",
}


def write_analytics_outputs(
    output_dir: Path, result: AnalyticsRunResult
) -> dict[str, int]:
    """Write all stable Feature 8 outputs and return deterministic row counts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for filename, attribute in ANALYTICS_OUTPUTS.items():
        rows = getattr(result, attribute)
        columns = (
            tuple(type(rows[0]).model_fields) if rows else _empty_columns(attribute)
        )
        counts[filename] = write_model_csv(output_dir / filename, rows, columns)

    summary = {
        "profile_code": result.profile_code,
        "input_cleaned_job_count": result.input_cleaned_job_count,
        "classifier_input_job_count": result.classifier_input_job_count,
        "included_job_count": result.included_job_count,
        "excluded_job_count": result.excluded_job_count,
        "review_job_count": result.review_job_count,
        "reconciliation_passed": result.reconciliation_passed,
        "output_row_counts": counts,
    }
    summary_path = output_dir / "analytics_run_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    counts[summary_path.name] = 1
    return counts


def _empty_columns(attribute: str) -> tuple[str, ...]:
    """Return stable headers when an aggregate legitimately has no rows."""
    from skill_compass.schemas import analytics as models

    model_by_attribute = {
        "job_facts": models.AnalyticsJobFact,
        "job_skill_facts": models.AnalyticsJobSkillFact,
        "skill_demand": models.SkillDemandMetric,
        "skill_role_demand": models.SkillRoleDemandMetric,
        "role_summary": models.RoleSummaryMetric,
        "role_seniority": models.RoleSeniorityMetric,
        "seniority_distribution": models.DistributionMetric,
        "state_distribution": models.DistributionMetric,
        "city_distribution": models.DistributionMetric,
        "employment_type_distribution": models.DistributionMetric,
        "work_mode_distribution": models.DistributionMetric,
        "skill_combinations": models.SkillCombinationMetric,
        "quality_metrics": models.AnalyticsQualityMetric,
    }
    return tuple(model_by_attribute[attribute].model_fields)
