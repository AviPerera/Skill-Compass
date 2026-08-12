"""Test explainable relevance decisions in the unit-test layer.

These sanitized tests exercise governed Feature 7 behavior and must not read
private datasets, call external services, or redefine production rules.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from skill_compass.classification.relevance import (
    RelevanceJobInput,
    classify_job_relevance,
    classify_profile_relevance,
)
from skill_compass.classification.relevance_config import load_relevance_rules
from skill_compass.schemas.classification import (
    JobRoleClassification,
    JobSeniorityClassification,
)
from skill_compass.schemas.extraction import JobRequirementMatch
from skill_compass.schemas.jobs import CleanedJob

RULES = load_relevance_rules(Path("profiles/data_analytics/relevance_rules.yaml"))
CLASSIFIED_AT = datetime(2026, 8, 13, 0, 0, tzinfo=UTC)


def _role(
    code: str,
    *,
    confidence: str = "high",
    score: str = "0.9000",
    review: bool = False,
    candidate: str | None = None,
) -> JobRoleClassification:
    """Build one fictional Feature 5 result without rerunning that feature."""
    labels = {
        "data_analyst": "Data Analyst",
        "business_analyst": "Business Analyst",
        "bi_analyst": "BI Analyst",
        "reporting_analyst": "Reporting Analyst",
        "data_scientist": "Data Scientist",
        "other": "Other",
        "review": "Review",
    }
    return JobRoleClassification(
        source_code="fixture_source",
        source_job_id="fixture-100",
        role_group_code=code,
        role_group_label=labels[code],
        role_confidence_score=Decimal(score),
        role_confidence_level=confidence,
        role_review_flag=review,
        role_reason="Fictional governed role evidence.",
        candidate_role_1_code=candidate,
        candidate_role_1_score=Decimal("0.6000") if candidate else None,
        role_classifier_version="0.1.0",
        role_rules_version="0.1.0",
        role_rules_hash="a" * 64,
    )


def _requirement(
    code: str, category: str, *, score: str = "0.9000"
) -> JobRequirementMatch:
    """Build one distinct fictional Feature 3 requirement result."""
    return JobRequirementMatch(
        source_code="fixture_source",
        source_job_id="fixture-100",
        requirement_code=code,
        requirement_name=code.replace("_", " ").title(),
        requirement_type="skill",
        category_code=category,
        category_name=category.replace("_", " ").title(),
        dashboard_group="Technical Skills",
        evidence_count=1,
        matched_sections=("description_text_clean",),
        matched_aliases=(code,),
        highest_section_weight=Decimal("0.7"),
        extraction_score=Decimal(score),
        confidence_level="high",
        extraction_method="deterministic_dictionary",
        dictionary_version="0.1.0",
        dictionary_hash="b" * 64,
        extractor_version="0.1.0",
        profile_version="0.1.0",
        extraction_output_schema_version="0.1.0",
    )


def _seniority_unknown() -> JobSeniorityClassification:
    """Build one Feature 6 Unknown result for independence tests."""
    return JobSeniorityClassification(
        source_code="fixture_source",
        source_job_id="fixture-100",
        seniority_code="unknown",
        seniority_label="Unknown",
        graduate_level_flag=False,
        seniority_confidence_score=Decimal("0"),
        seniority_confidence_level="low",
        seniority_review_flag=False,
        seniority_conflict_flag=False,
        seniority_reason="No governed seniority evidence.",
        seniority_classifier_version="0.1.0",
        seniority_rules_version="0.1.0",
        seniority_rules_hash="c" * 64,
    )


def _item(
    job: CleanedJob,
    role: JobRoleClassification,
    requirements: tuple[JobRequirementMatch, ...] = (),
    seniority: JobSeniorityClassification | None = None,
) -> RelevanceJobInput:
    """Align fictional upstream identities to one canonical job."""
    values = role.model_dump()
    values["source_code"] = job.source_code
    values["source_job_id"] = job.source_job_id
    aligned_role = JobRoleClassification.model_validate(values)
    aligned_requirements = tuple(
        JobRequirementMatch.model_validate(
            {
                **requirement.model_dump(),
                "source_code": job.source_code,
                "source_job_id": job.source_job_id,
            }
        )
        for requirement in requirements
    )
    aligned_seniority = None
    if seniority is not None:
        aligned_seniority = JobSeniorityClassification.model_validate(
            {
                **seniority.model_dump(),
                "source_code": job.source_code,
                "source_job_id": job.source_job_id,
            }
        )
    return RelevanceJobInput(
        job=job,
        role=aligned_role,
        requirements=aligned_requirements,
        seniority=aligned_seniority,
    )


@pytest.mark.parametrize(
    ("title", "description", "role_code", "requirements"),
    (
        (
            "Data Analyst",
            "Analyse data, query data and produce actionable insights.",
            "data_analyst",
            (("sql", "database"), ("power_bi", "business_intelligence")),
        ),
        (
            "Business Analyst",
            "Lead requirements gathering, process mapping and stakeholder workshops.",
            "business_analyst",
            (("business_analysis", "business_analysis"),),
        ),
        (
            "BI Analyst",
            "Develop dashboards, provide data visualisation and management reporting.",
            "bi_analyst",
            (("power_bi", "business_intelligence"), ("dax", "business_intelligence")),
        ),
        (
            "Reporting Analyst",
            "Own performance reporting, management reporting and interpret trends.",
            "reporting_analyst",
            (("reporting", "business_intelligence"),),
        ),
        (
            "Data Scientist",
            "Perform statistical analysis, predictive modelling and machine learning.",
            "data_scientist",
            (("statistics", "data_science"), ("machine_learning", "data_science")),
        ),
    ),
)
def test_clear_approved_roles_are_included_with_independent_support(
    cleaned_job_factory: Callable[..., CleanedJob],
    title: str,
    description: str,
    role_code: str,
    requirements: tuple[tuple[str, str], ...],
) -> None:
    job = cleaned_job_factory(
        title_raw=title, title_clean=title, description_text_clean=description
    )
    item = _item(
        job,
        _role(role_code),
        tuple(_requirement(code, category) for code, category in requirements),
    )

    result, evidence = classify_job_relevance(item, RULES, classified_at=CLASSIFIED_AT)

    assert result.relevance_status == "included"
    assert result.relevance_review_flag is False
    assert {row.evidence_family for row in evidence} >= {"role", "title"}


def test_missing_description_does_not_force_review(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        description_text_clean=None,
        usable_description_status="missing",
        analytically_eligible=False,
        summary_text_clean="Analyse data and produce insights.",
    )
    item = _item(
        job,
        _role("data_analyst"),
        (
            _requirement("sql", "database"),
            _requirement("power_bi", "business_intelligence"),
        ),
        _seniority_unknown(),
    )

    result, _ = classify_job_relevance(item, RULES, classified_at=CLASSIFIED_AT)

    assert result.relevance_status == "included"
    assert "missing_description" in result.relevance_quality_flags


def test_missing_title_can_be_resolved_by_role_responsibilities_and_requirements(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="",
        title_clean="",
        description_text_clean=(
            "Analyse data, query data and develop dashboards for actionable insights."
        ),
    )
    item = _item(
        job,
        _role("data_analyst"),
        (
            _requirement("sql", "database"),
            _requirement("power_bi", "business_intelligence"),
        ),
    )

    result, _ = classify_job_relevance(item, RULES, classified_at=CLASSIFIED_AT)

    assert result.relevance_status == "included"
    assert "missing_title" in result.relevance_quality_flags


def test_generic_analyst_with_strong_multifamily_evidence_is_included(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Analyst",
        title_clean="Analyst",
        description_text_clean=(
            "Analyse data, query data, develop dashboards and produce actionable insights."
        ),
    )
    item = _item(
        job,
        _role("review", review=True, candidate="data_analyst", score="0.6000"),
        (
            _requirement("sql", "database"),
            _requirement("power_bi", "business_intelligence"),
        ),
    )

    result, _ = classify_job_relevance(item, RULES, classified_at=CLASSIFIED_AT)

    assert result.relevance_status == "included"
    assert result.evidence_family_count >= 3


def test_requirements_support_but_cannot_independently_force_inclusion(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Project Officer",
        title_clean="Project Officer",
        description_text_clean="Coordinate a small fictional project.",
    )
    item = _item(
        job,
        _role("other", confidence="low", score="0.0000"),
        (
            _requirement("sql", "database"),
            _requirement("power_bi", "business_intelligence"),
            _requirement("python", "programming"),
        ),
    )

    result, _ = classify_job_relevance(item, RULES, classified_at=CLASSIFIED_AT)

    assert result.relevance_status == "review"
    assert result.relevance_reason_code == "weak_relevance_signal"


def test_weak_source_or_requirement_signals_do_not_create_unnecessary_review(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Operations Coordinator",
        title_clean="Operations Coordinator",
        classification_raw="Information & Communication Technology",
        subclassification_raw="Analysts",
        description_text_clean=(
            "Coordinate fictional operational schedules, suppliers and administrative services."
        ),
    )
    item = _item(
        job,
        _role("other", confidence="low", score="0.0000"),
        (_requirement("excel", "spreadsheet", score="0.5000"),),
    )

    result, _ = classify_job_relevance(item, RULES, classified_at=CLASSIFIED_AT)

    assert result.relevance_status == "excluded"
    assert result.relevance_reason_code == "clear_irrelevance"


def test_repeated_weak_keyword_cannot_overpower_negative_context(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Application Support Analyst",
        title_clean="Application Support Analyst",
        description_text_clean=(
            ("Data analysis. " * 30)
            + "Resolve support tickets, troubleshoot software and provide application support."
        ),
    )
    item = _item(job, _role("other", confidence="low", score="0.0500"))

    result, evidence = classify_job_relevance(item, RULES, classified_at=CLASSIFIED_AT)

    assert result.relevance_status == "excluded"
    assert sum(row.evidence_term == "data analysis" for row in evidence) == 1


@pytest.mark.parametrize(
    ("title", "description"),
    (
        (
            "Management Accountant",
            "Prepare tax returns, statutory accounting and accounts payable reconciliations.",
        ),
        (
            "Sales Administrator",
            "Perform sales administration, cold calling and coordinate customer orders.",
        ),
        (
            "Sales Analyst",
            "Perform sales administration, cold calling and coordinate customer orders.",
        ),
        (
            "Warehouse Coordinator",
            "Manage warehouse operations, staff rosters and stock movements with data entry.",
        ),
        (
            "Research Fellow",
            "Conduct academic research and teach undergraduate classes in an unrelated field.",
        ),
    ),
)
def test_clear_unrelated_jobs_are_excluded_not_unnecessary_review(
    cleaned_job_factory: Callable[..., CleanedJob], title: str, description: str
) -> None:
    job = cleaned_job_factory(
        title_raw=title, title_clean=title, description_text_clean=description
    )

    result, _ = classify_job_relevance(
        _item(job, _role("other", confidence="low", score="0.0000")),
        RULES,
        classified_at=CLASSIFIED_AT,
    )

    assert result.relevance_status == "excluded"


@pytest.mark.parametrize(
    ("title", "description", "reason"),
    (
        ("Analyst", "Support a small team.", "generic_analyst_title"),
        (
            "Analytics Engineer",
            "Build data models and analytics infrastructure with SQL.",
            "adjacent_role",
        ),
        (
            "Coordinator",
            "Coordinate tasks.",
            "insufficient_evidence",
        ),
    ),
)
def test_genuine_ambiguity_remains_review(
    cleaned_job_factory: Callable[..., CleanedJob],
    title: str,
    description: str,
    reason: str,
) -> None:
    job = cleaned_job_factory(
        title_raw=title, title_clean=title, description_text_clean=description
    )

    result, _ = classify_job_relevance(
        _item(job, _role("other", confidence="low", score="0.0500")),
        RULES,
        classified_at=CLASSIFIED_AT,
    )

    assert result.relevance_status == "review"
    assert result.relevance_reason_code == reason


def test_strong_requirements_conflicting_with_unrelated_title_stay_review(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        title_raw="Software Engineer",
        title_clean="Software Engineer",
        description_text_clean=(
            "Build application services. SQL, Power BI and Python are listed as desirable."
        ),
    )
    item = _item(
        job,
        _role("other", confidence="low", score="0.1000"),
        (
            _requirement("sql", "database"),
            _requirement("power_bi", "business_intelligence"),
            _requirement("python", "programming"),
        ),
    )

    result, _ = classify_job_relevance(item, RULES, classified_at=CLASSIFIED_AT)

    assert result.relevance_status == "review"
    assert result.relevance_reason_code == "conflicting_role_evidence"


def test_analytics_title_with_unrelated_responsibilities_stays_review(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        description_text_clean=(
            "Resolve support tickets, troubleshoot software and provide application support."
        )
    )
    item = _item(job, _role("data_analyst"))

    result, _ = classify_job_relevance(item, RULES, classified_at=CLASSIFIED_AT)

    assert result.relevance_status == "review"
    assert result.relevance_reason_code == "conflicting_role_evidence"


def test_unknown_seniority_does_not_change_relevance_decision(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    job = cleaned_job_factory(
        description_text_clean="Analyse data, query data and develop dashboards."
    )
    requirements = (_requirement("sql", "database"),)
    without = _item(job, _role("data_analyst"), requirements)
    with_unknown = _item(job, _role("data_analyst"), requirements, _seniority_unknown())

    first, first_evidence = classify_job_relevance(
        without, RULES, classified_at=CLASSIFIED_AT
    )
    second, second_evidence = classify_job_relevance(
        with_unknown, RULES, classified_at=CLASSIFIED_AT
    )

    assert first == second
    assert first_evidence == second_evidence
    assert first.relevance_status == "included"


def test_run_is_deterministic_bounded_and_reconciled(
    cleaned_job_factory: Callable[..., CleanedJob],
) -> None:
    relevant = cleaned_job_factory(
        source_job_id="relevant",
        description_text_clean="Analyse data, query data and develop dashboards.",
    )
    unrelated = cleaned_job_factory(
        source_job_id="unrelated",
        title_raw="Operations Coordinator",
        title_clean="Operations Coordinator",
        description_text_clean=(
            "Coordinate fictional operational schedules, services and administrative tasks."
        ),
    )
    inputs = (
        _item(relevant, _role("data_analyst"), (_requirement("sql", "database"),)),
        _item(unrelated, _role("other", confidence="low", score="0.0000")),
    )

    first = classify_profile_relevance(inputs, RULES, classified_at=CLASSIFIED_AT)
    second = classify_profile_relevance(inputs, RULES, classified_at=CLASSIFIED_AT)

    assert first == second
    assert first.reconciliation_passed is True
    assert first.summary.total_classifier_input == 2
    assert (
        first.summary.included_count
        + first.summary.excluded_count
        + first.summary.review_count
        == 2
    )
    assert all(
        Decimal("0") <= row.relevance_score <= Decimal("1")
        for row in first.classifications
    )
    assert all(
        len(row.evidence_term) <= RULES.limits.evidence_term_max_length
        and len(row.context_snippet) <= RULES.limits.context_snippet_max_length
        for row in first.evidence
    )
