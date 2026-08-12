"""Test Feature 7 chart rendering in the unit-test layer.

These tests use sanitized typed results and must not alter relevance decisions,
read private datasets, or implement production chart policy.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from skill_compass.classification.relevance import (
    RelevanceJobInput,
    classify_profile_relevance,
)
from skill_compass.classification.relevance_config import load_relevance_rules
from skill_compass.reporting.profile_relevance_charts import (
    generate_profile_relevance_charts,
)
from skill_compass.schemas.classification import JobRoleClassification
from skill_compass.schemas.jobs import CleanedJob


def _role(job: CleanedJob, code: str) -> JobRoleClassification:
    """Build a minimal aligned role result for chart-only testing."""
    return JobRoleClassification(
        source_code=job.source_code,
        source_job_id=job.source_job_id,
        role_group_code=code,
        role_group_label="Data Analyst" if code == "data_analyst" else "Other",
        role_confidence_score=Decimal("0.9")
        if code == "data_analyst"
        else Decimal("0"),
        role_confidence_level="high" if code == "data_analyst" else "low",
        role_review_flag=False,
        role_reason="Fictional chart evidence.",
        role_classifier_version="0.1.0",
        role_rules_version="0.1.0",
        role_rules_hash="a" * 64,
    )


def test_profile_relevance_charts_use_calculated_results(
    tmp_path: Path, cleaned_job_factory: Callable[..., CleanedJob]
) -> None:
    rules = load_relevance_rules(Path("profiles/data_analytics/relevance_rules.yaml"))
    relevant = cleaned_job_factory(
        source_job_id="chart-relevant",
        description_text_clean="Analyse data, query data and develop dashboards.",
    )
    unrelated = cleaned_job_factory(
        source_job_id="chart-unrelated",
        title_raw="Operations Coordinator",
        title_clean="Operations Coordinator",
        description_text_clean=(
            "Coordinate fictional operational schedules and administrative services."
        ),
    )
    result = classify_profile_relevance(
        (
            RelevanceJobInput(relevant, _role(relevant, "data_analyst")),
            RelevanceJobInput(unrelated, _role(unrelated, "other")),
        ),
        rules,
        classified_at=datetime(2026, 8, 13, tzinfo=UTC),
    )

    charts = generate_profile_relevance_charts(result, tmp_path)

    assert {chart.path.name for chart in charts} == {
        "profile_relevance_distribution.png",
        "top_review_reasons.png",
    }
    assert all(chart.path.stat().st_size > 0 for chart in charts)
    assert charts[0].plotted_items == 3
