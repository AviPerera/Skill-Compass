"""Test saved Feature 6 charts from typed seniority results."""

from collections.abc import Callable
from pathlib import Path

from skill_compass.classification.seniority import classify_seniority
from skill_compass.classification.seniority_config import load_seniority_rules
from skill_compass.reporting.seniority_classification_charts import (
    generate_seniority_classification_charts,
)
from skill_compass.schemas.jobs import CleanedJob


def test_seniority_charts_use_reconciled_calculated_results(
    tmp_path: Path, cleaned_job_factory: Callable[..., CleanedJob]
) -> None:
    rules = load_seniority_rules(Path("profiles/data_analytics/seniority_rules.yaml"))
    result = classify_seniority(
        (
            cleaned_job_factory(
                source_job_id="chart-junior",
                title_raw="Junior Data Analyst",
                title_clean="Junior Data Analyst",
            ),
            cleaned_job_factory(source_job_id="chart-unknown"),
        ),
        rules,
    )

    charts = generate_seniority_classification_charts(result, tmp_path)

    assert {chart.path.name for chart in charts} == {
        "seniority_distribution.png",
        "seniority_confidence_distribution.png",
    }
    assert all(chart.path.stat().st_size > 0 for chart in charts)
    assert charts[0].plotted_items == 6
    assert charts[1].plotted_items == 3
