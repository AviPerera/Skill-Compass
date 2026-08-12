"""Test explainable seniority decisions, conflicts, and safety outcomes."""

from collections.abc import Callable
from pathlib import Path

import pytest

from skill_compass.classification.seniority import (
    classify_job_seniority,
    classify_seniority,
)
from skill_compass.classification.seniority_config import load_seniority_rules
from skill_compass.schemas.jobs import CleanedJob

RULES = load_seniority_rules(Path("profiles/data_analytics/seniority_rules.yaml"))


@pytest.mark.parametrize(
    ("title", "description", "expected_code", "expected_rank", "graduate_flag"),
    (
        ("Graduate Data Analyst", "Recent graduate.", "entry_level", 1, True),
        ("Junior Data Analyst", "Work under guidance.", "junior", 2, True),
        ("Intermediate Data Analyst", "Work independently.", "mid_level", 3, False),
        ("Senior Data Analyst", "Mentor junior analysts.", "senior", 4, False),
    ),
)
def test_explicit_titles_map_to_the_approved_ordered_levels(
    cleaned_job_factory: Callable[..., CleanedJob],
    title: str,
    description: str,
    expected_code: str,
    expected_rank: int,
    graduate_flag: bool,
) -> None:
    job = cleaned_job_factory(
        title_raw=title,
        title_clean=title,
        description_text_clean=description,
    )

    result, evidence = classify_job_seniority(job, RULES)

    assert result.seniority_code == expected_code
    assert result.seniority_rank == expected_rank
    assert result.graduate_level_flag is graduate_flag
    assert result.seniority_review_flag is False
    assert any(row.evidence_section == "title_clean" for row in evidence)


def test_generic_title_does_not_default_to_mid_level(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        description_text_clean="Build fictional analytics outputs."
    )

    result, evidence = classify_job_seniority(job, RULES)

    assert result.seniority_code == "unknown"
    assert result.seniority_rank is None
    assert result.graduate_level_flag is False
    assert evidence == ()


def test_meaningful_but_sub_threshold_context_is_review(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        summary_text_clean=(
            "Work independently with end to end delivery and manage own workload."
        )
    )

    result, evidence = classify_job_seniority(job, RULES)

    assert result.seniority_code == "review"
    assert result.seniority_review_flag is True
    assert result.candidate_seniority_1_code == "mid_level"
    assert len(evidence) == 3


def test_dual_explicit_title_markers_enter_review(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Junior / Senior Data Analyst",
        title_clean="Junior / Senior Data Analyst",
    )

    result, _ = classify_job_seniority(job, RULES)

    assert result.seniority_code == "review"
    assert result.seniority_conflict_flag is True
    assert result.candidate_seniority_1_score == result.candidate_seniority_2_score


def test_distant_title_and_experience_evidence_enters_review(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Junior Data Analyst",
        title_clean="Junior Data Analyst",
        description_text_clean="Requires 8 years of relevant experience.",
    )

    result, evidence = classify_job_seniority(job, RULES)

    assert result.seniority_code == "review"
    assert result.seniority_conflict_flag is True
    assert any(
        row.seniority_code == "senior"
        and row.evidence_type == "experience"
        and row.experience_years_min == 8
        for row in evidence
    )


def test_year_ranges_and_apostrophes_are_parsed_as_bounded_evidence(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Intermediate Data Analyst",
        title_clean="Intermediate Data Analyst",
        description_text_clean="Requires 3-4 years' professional experience.",
    )

    result, evidence = classify_job_seniority(job, RULES)

    years = [row for row in evidence if row.evidence_type == "experience"]
    assert result.seniority_code == "mid_level"
    assert len(years) == 1
    assert years[0].experience_years_min == 3
    assert years[0].experience_years_max == 4


def test_open_ended_experience_preserves_the_plus_boundary(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Senior Data Analyst",
        title_clean="Senior Data Analyst",
        description_text_clean="Requires 6+ years of industry experience.",
    )

    result, evidence = classify_job_seniority(job, RULES)

    years = [row for row in evidence if row.evidence_type == "experience"]
    assert result.seniority_code == "senior"
    assert len(years) == 1
    assert years[0].experience_years_min == 6
    assert years[0].experience_years_max is None


def test_relationship_language_and_partial_lead_term_do_not_imply_seniority(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    report = cleaned_job_factory(
        source_job_id="reporting-line",
        description_text_clean="The role reports to a senior manager.",
    )
    lead_generation = cleaned_job_factory(
        source_job_id="lead-generation",
        title_raw="Lead Generation Analyst",
        title_clean="Lead Generation Analyst",
    )

    report_result, _ = classify_job_seniority(report, RULES)
    lead_result, _ = classify_job_seniority(lead_generation, RULES)

    assert report_result.seniority_code == "unknown"
    assert lead_result.seniority_code == "unknown"


def test_missing_fields_are_counted_and_all_outcomes_reconcile(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    missing_title = cleaned_job_factory(
        source_job_id="missing-title",
        title_raw="",
        title_clean="",
        summary_text_clean="Recent graduate with training provided.",
    )
    missing_description = cleaned_job_factory(
        source_job_id="missing-description",
        title_raw="Senior Data Analyst",
        title_clean="Senior Data Analyst",
        description_text_clean=None,
        usable_description_status="missing",
        analytically_eligible=False,
    )

    run = classify_seniority((missing_title, missing_description), RULES)

    assert run.quality.missing_title_count == 1
    assert run.quality.missing_description_count == 1
    assert sum(row.job_count for row in run.distribution) == 2
    assert len(run.classifications) == 2
    assert run.reconciliation_passed is True


def test_repeated_execution_is_deterministic_and_evidence_is_bounded(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Senior Data Analyst",
        title_clean="Senior Data Analyst",
        description_text_clean=("Mentor junior analysts and lead delivery. " * 1000),
    )

    first = classify_seniority((job,), RULES)
    second = classify_seniority((job,), RULES)

    assert first == second
    assert all(
        len(row.evidence_term) <= RULES.evidence_term_max_length
        for row in first.evidence
    )
    assert sum(row.evidence_term == "lead delivery" for row in first.evidence) == 1
