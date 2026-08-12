"""Test deterministic explainable role decisions and ambiguity controls."""

from collections.abc import Callable
from pathlib import Path

import pytest

from skill_compass.classification.config import load_role_rules
from skill_compass.classification.roles import classify_job_role, classify_roles
from skill_compass.schemas.jobs import CleanedJob

RULES = load_role_rules(Path("profiles/data_analytics/role_rules.yaml"))


@pytest.mark.parametrize(
    ("title", "description", "expected_code"),
    (
        (
            "Data Analyst",
            "Perform data analysis, query SQL datasets and provide data insights.",
            "data_analyst",
        ),
        (
            "Business Analyst",
            "Lead requirements gathering, stakeholder workshops and process improvement.",
            "business_analyst",
        ),
        (
            "Business Intelligence Analyst",
            "Develop Power BI solutions, DAX measures and semantic models.",
            "bi_analyst",
        ),
        (
            "Reporting Analyst",
            "Own management reporting, report production and monthly reporting.",
            "reporting_analyst",
        ),
        (
            "Data Scientist",
            "Build machine learning, predictive modelling and statistical modelling solutions.",
            "data_scientist",
        ),
    ),
)
def test_explicit_role_titles_require_and_use_context(
    cleaned_job_factory: Callable[..., CleanedJob],
    title: str,
    description: str,
    expected_code: str,
) -> None:
    job = cleaned_job_factory(
        title_raw=title, title_clean=title, description_text_clean=description
    )

    result, evidence = classify_job_role(job, RULES)

    assert result.role_group_code == expected_code
    assert result.role_review_flag is False
    assert {row.evidence_section for row in evidence} >= {
        "title_clean",
        "description_text_clean",
    }


@pytest.mark.parametrize(
    ("title", "description"),
    (
        (
            "Data Analyst / BI Analyst",
            "Combine data analysis with business intelligence delivery.",
        ),
        (
            "Data Analyst / Reporting Analyst",
            "Combine data analysis with management reporting.",
        ),
        (
            "Data Analyst / Business Analyst",
            "Combine data analysis with requirements gathering.",
        ),
        (
            "Data Analyst / Data Scientist",
            "Combine data analysis with machine learning.",
        ),
    ),
)
def test_related_role_ambiguity_enters_review(
    cleaned_job_factory: Callable[..., CleanedJob], title: str, description: str
) -> None:
    job = cleaned_job_factory(
        title_raw=title, title_clean=title, description_text_clean=description
    )

    result, _ = classify_job_role(job, RULES)

    assert result.role_group_code == "review"
    assert result.role_review_flag is True
    assert result.candidate_role_1_code is not None
    assert result.candidate_role_2_code is not None


def test_exact_tie_is_review_not_configuration_order_precedence(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Data Analyst / BI Analyst",
        title_clean="Data Analyst / BI Analyst",
        description_text_clean="Data analysis and business intelligence.",
    )

    result, _ = classify_job_role(job, RULES)

    assert result.role_group_code == "review"
    assert result.candidate_role_1_score == result.candidate_role_2_score


def test_near_tie_inside_margin_is_review(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Data Analyst / BI Analyst",
        title_clean="Data Analyst / BI Analyst",
        summary_text_clean="Data analysis and Power BI.",
        classification_raw="Database Development & Administration",
        description_text_clean="Deliver governed analytical outputs.",
    )

    result, _ = classify_job_role(job, RULES)

    assert result.role_group_code == "review"
    assert result.candidate_role_1_score is not None
    assert result.candidate_role_2_score is not None
    assert abs(result.candidate_role_1_score - result.candidate_role_2_score) <= (
        RULES.thresholds.ambiguity_margin
    )


def test_clear_winner_outside_margin_is_classified(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        description_text_clean=(
            "Perform data analysis, query SQL datasets and deliver data insights. "
            "Power BI exposure is useful."
        )
    )

    result, _ = classify_job_role(job, RULES)

    assert result.role_group_code == "data_analyst"
    assert result.role_review_flag is False


def test_weak_or_absent_role_evidence_is_other(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Operations Coordinator",
        title_clean="Operations Coordinator",
        description_text_clean="Coordinate fictional schedules and services.",
    )

    result, evidence = classify_job_role(job, RULES)

    assert result.role_group_code == "other"
    assert result.role_review_flag is False
    assert result.candidate_role_1_code is None
    assert evidence == ()


def test_meaningful_conflicting_title_evidence_is_review(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Data Analyst / Data Engineer",
        title_clean="Data Analyst / Data Engineer",
        description_text_clean="Perform data analysis and query SQL datasets.",
    )

    result, evidence = classify_job_role(job, RULES)

    assert result.role_group_code == "review"
    assert any(row.evidence_type == "exclusion_title" for row in evidence)


@pytest.mark.parametrize(
    ("title", "description", "forbidden_code"),
    (
        (
            "Data Analyst",
            "Exposure to machine learning is desirable.",
            "data_scientist",
        ),
        (
            "Business Analyst",
            "Requirements gathering with Power BI experience preferred.",
            "bi_analyst",
        ),
        (
            "Data Analyst",
            "Perform data analysis and prepare monthly reports.",
            "reporting_analyst",
        ),
        (
            "BI Analyst",
            "Develop Power BI dashboards with stakeholder management.",
            "business_analyst",
        ),
    ),
)
def test_single_technology_or_context_mention_does_not_override_title(
    cleaned_job_factory: Callable[..., CleanedJob],
    title: str,
    description: str,
    forbidden_code: str,
) -> None:
    job = cleaned_job_factory(
        title_raw=title, title_clean=title, description_text_clean=description
    )

    result, _ = classify_job_role(job, RULES)

    assert result.role_group_code != forbidden_code


def test_title_only_evidence_is_review(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        description_text_clean="Coordinate schedules and services."
    )

    result, _ = classify_job_role(job, RULES)

    assert result.role_group_code == "review"
    assert "lacks non-title" in result.role_reason


def test_missing_title_and_missing_description_are_handled(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    missing_title = cleaned_job_factory(
        source_job_id="missing-title",
        title_raw="",
        title_clean="",
        description_text_clean="Data analysis, SQL and data insights.",
    )
    missing_description = cleaned_job_factory(
        source_job_id="missing-description",
        summary_text_clean="Perform data analysis and query SQL datasets.",
        description_text_clean=None,
        usable_description_status="missing",
        analytically_eligible=False,
    )

    run = classify_roles((missing_title, missing_description), RULES)

    assert run.quality.missing_title_count == 1
    assert run.quality.missing_description_count == 1
    assert len(run.classifications) == 2
    assert run.classifications[1].role_group_code == "data_analyst"


def test_repeated_execution_is_deterministic_and_evidence_is_bounded(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        description_text_clean=("Data analysis and SQL. " * 1000),
    )

    first = classify_roles((job,), RULES)
    second = classify_roles((job,), RULES)

    assert first == second
    assert all(
        len(row.evidence_term) <= RULES.evidence_term_max_length
        for row in first.evidence
    )
    assert sum(row.evidence_term == "data analysis" for row in first.evidence) == 1


def test_company_name_and_source_classification_cannot_determine_role(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Coordinator",
        title_clean="Coordinator",
        company_name_clean="Data Scientist Business Intelligence Reporting",
        classification_raw="Analysts",
        subclassification_raw="Analysis & Reporting",
        description_text_clean="Coordinate fictional services.",
    )

    result, _ = classify_job_role(job, RULES)

    assert result.role_group_code == "other"
