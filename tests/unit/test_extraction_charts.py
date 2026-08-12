"""Test non-interactive Feature 3 graph data and PNG generation."""

from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from skill_compass.adapters.extraction_csv import read_cleaned_jobs_csv
from skill_compass.extraction.dictionary import load_requirement_dictionary
from skill_compass.extraction.profile import load_extraction_profile
from skill_compass.extraction.service import extract_requirements
from skill_compass.reporting.skill_extraction_charts import (
    generate_extraction_charts,
    skill_count_distribution,
    top_skill_series,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = PROJECT_ROOT / "profiles/data_analytics/profile.yaml"
DICTIONARY_PATH = PROJECT_ROOT / "profiles/data_analytics/requirements.csv"
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/cleaned_jobs.csv"


def extraction_result():
    """Build typed extraction results from the sanitised cleaned fixture."""
    profile = load_extraction_profile(PROFILE_PATH)
    dictionary = load_requirement_dictionary(DICTIONARY_PATH, profile)
    return extract_requirements(
        read_cleaned_jobs_csv(FIXTURE_PATH), profile, dictionary
    )


def test_chart_series_use_distinct_jobs_and_include_zero_skill_jobs() -> None:
    result = extraction_result()
    series = top_skill_series(result, 15)
    distribution = skill_count_distribution(result)

    demand_lookup = {
        row.requirement_name: row.matched_job_count for row in result.skill_demand[:15]
    }
    assert {name: count for name, count, _ in series} == demand_lookup
    assert distribution == (
        (0, 1),
        (1, 0),
        (2, 0),
        (3, 0),
        (4, 0),
        (5, 1),
        (6, 0),
        (7, 0),
        (8, 1),
    )


def test_both_pngs_are_non_empty_without_showing_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    show_calls = 0

    def record_show() -> None:
        nonlocal show_calls
        show_calls += 1

    monkeypatch.setattr(plt, "show", record_show)
    charts = generate_extraction_charts(extraction_result(), tmp_path)

    assert show_calls == 0
    assert plt.isinteractive() is False
    assert {chart.path.name for chart in charts} == {
        "top_15_skills_by_job_count.png",
        "skills_per_job_distribution.png",
    }
    for chart in charts:
        assert chart.path.stat().st_size > 0
        assert chart.path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
