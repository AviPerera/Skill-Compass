"""Test deterministic job aggregation, demand denominators, and quality metrics."""

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from skill_compass.adapters.extraction_csv import read_cleaned_jobs_csv
from skill_compass.extraction.dictionary import load_requirement_dictionary
from skill_compass.extraction.profile import load_extraction_profile
from skill_compass.extraction.service import extract_requirements
from skill_compass.schemas.jobs import CleanedJob

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = PROJECT_ROOT / "profiles/data_analytics/profile.yaml"
DICTIONARY_PATH = PROJECT_ROOT / "profiles/data_analytics/requirements.csv"
CLEANED_FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/cleaned_jobs.csv"


def configuration():
    """Load the repository extraction profile and requirement dictionary."""
    profile = load_extraction_profile(PROFILE_PATH)
    return profile, load_requirement_dictionary(DICTIONARY_PATH, profile)


def metric_value(result, name: str) -> str:
    """Return one unique string quality value from an extraction result."""
    return next(
        metric.metric_value
        for metric in result.quality_metrics
        if metric.metric_name == name
    )


def test_repeated_evidence_aggregates_to_one_job_requirement(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    profile, dictionary = configuration()
    job = cleaned_job_factory(
        title_clean="SQL Analyst",
        summary_text_clean="Use SQL",
        bullet_points_clean=("SQL reporting",),
        description_text_clean="Build fictional outputs using SQL and SQL.",
    )

    result = extract_requirements((job,), profile, dictionary)
    sql_matches = [
        match
        for match in result.job_requirement_matches
        if match.requirement_code == "sql"
    ]

    assert len(sql_matches) == 1
    assert sql_matches[0].evidence_count == 5
    assert sql_matches[0].matched_sections == (
        "title_clean",
        "summary_text_clean",
        "bullet_points_clean",
        "description_text_clean",
    )
    assert sql_matches[0].confidence_level == "high"


def test_stronger_section_weight_increases_extraction_score(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    profile, dictionary = configuration()
    title_job = cleaned_job_factory(
        source_job_id="title-job",
        title_clean="SQL Analyst",
        description_text_clean="Build fictional outputs.",
    )
    description_job = cleaned_job_factory(
        source_job_id="description-job",
        title_clean="Analyst",
        description_text_clean="Build fictional outputs with SQL.",
    )

    result = extract_requirements((title_job, description_job), profile, dictionary)
    scores = {
        match.source_job_id: match.extraction_score
        for match in result.job_requirement_matches
        if match.requirement_code == "sql"
    }

    assert scores["title-job"] > scores["description-job"]


def test_fixture_demand_uses_distinct_eligible_jobs_and_includes_zero_skills() -> None:
    profile, dictionary = configuration()
    jobs = read_cleaned_jobs_csv(CLEANED_FIXTURE_PATH)

    result = extract_requirements(jobs, profile, dictionary)
    demand = {row.requirement_code: row for row in result.skill_demand}

    assert result.input_cleaned_jobs == 4
    assert result.analytically_eligible_jobs == 3
    assert result.skipped_jobs == 1
    assert demand["sql"].matched_job_count == 1
    assert demand["sql"].eligible_job_count == 3
    assert demand["sql"].demand_rate == Decimal("0.333333")
    assert demand["power_bi"].matched_job_count == 1
    assert demand["numpy"].matched_job_count == 0
    assert demand["numpy"].demand_rate == 0
    assert len(result.skill_demand) == 31
    assert [row.rank_overall for row in result.skill_demand] == list(range(1, 32))


def test_job_status_and_quality_counts_reconcile_fixture() -> None:
    profile, dictionary = configuration()
    jobs = read_cleaned_jobs_csv(CLEANED_FIXTURE_PATH)

    result = extract_requirements(jobs, profile, dictionary)
    statuses = {
        summary.source_job_id: summary.extraction_status
        for summary in result.job_summaries
    }

    assert statuses == {
        "fixture-201": "extracted",
        "fixture-202": "extracted",
        "fixture-203": "no_requirements_detected",
        "fixture-204": "skipped_ineligible",
    }
    assert len(result.job_requirement_matches) == 13
    assert len(result.evidence) == 16
    assert result.suppressed_negative_context_count == 2
    assert metric_value(result, "reconciliation_pass") == "true"
    assert metric_value(result, "match_evidence_reconciliation_pass") == "true"
    assert metric_value(result, "jobs_with_no_requirements") == "1"
    assert metric_value(result, "average_requirements_per_eligible_job") == "4.3333"
    assert metric_value(result, "median_requirements_per_eligible_job") == "5.0000"
    assert metric_value(result, "minimum_requirements_per_eligible_job") == "0"
    assert metric_value(result, "maximum_requirements_per_eligible_job") == "8"
