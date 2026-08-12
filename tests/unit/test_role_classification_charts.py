"""Test saved Feature 5 charts from typed classification results."""

from collections.abc import Callable
from pathlib import Path

from skill_compass.classification.config import load_role_rules
from skill_compass.classification.roles import classify_roles
from skill_compass.reporting.role_classification_charts import (
    generate_role_classification_charts,
)
from skill_compass.schemas.jobs import CleanedJob


def test_role_charts_use_reconciled_calculated_results(
    tmp_path: Path, cleaned_job_factory: Callable[..., CleanedJob]
) -> None:
    rules = load_role_rules(Path("profiles/data_analytics/role_rules.yaml"))
    result = classify_roles(
        (
            cleaned_job_factory(
                source_job_id="chart-data",
                description_text_clean="Data analysis, SQL and data insights.",
            ),
            cleaned_job_factory(
                source_job_id="chart-other",
                title_raw="Operations Coordinator",
                title_clean="Operations Coordinator",
                description_text_clean="Coordinate schedules and services.",
            ),
        ),
        rules,
    )

    charts = generate_role_classification_charts(result, tmp_path)

    assert {chart.path.name for chart in charts} == {
        "role_distribution.png",
        "role_confidence_distribution.png",
    }
    assert all(chart.path.stat().st_size > 0 for chart in charts)
    assert charts[0].plotted_items == 7
    assert charts[1].plotted_items == 3
