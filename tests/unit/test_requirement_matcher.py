"""Test deterministic boundary, phrase, section, overlap, and evidence controls."""

from collections.abc import Callable
from pathlib import Path

import pytest

from skill_compass.extraction.dictionary import load_requirement_dictionary
from skill_compass.extraction.matcher import extract_job_evidence
from skill_compass.extraction.profile import load_extraction_profile
from skill_compass.schemas.jobs import CleanedJob

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = PROJECT_ROOT / "profiles/data_analytics/profile.yaml"
DICTIONARY_PATH = PROJECT_ROOT / "profiles/data_analytics/requirements.csv"


@pytest.fixture
def extraction_config():
    """Load the approved profile and dictionary once per focused test."""
    profile = load_extraction_profile(PROFILE_PATH)
    dictionary = load_requirement_dictionary(DICTIONARY_PATH, profile)
    return profile, dictionary


def accepted_codes(result) -> list[str]:
    """Return requirement codes for accepted evidence in stable output order."""
    return [
        row.requirement_code
        for row in result.evidence
        if row.evidence_status == "accepted"
    ]


def test_token_boundaries_prevent_short_and_substring_false_positives(
    cleaned_job_factory: Callable[..., CleanedJob], extraction_config
) -> None:
    profile, dictionary = extraction_config
    job = cleaned_job_factory(
        title_clean="Reporting Coordinator",
        description_text_clean="Grow reliable NoSQL services with bright teams.",
    )

    result = extract_job_evidence(job, profile, dictionary)

    assert "r" not in accepted_codes(result)
    assert "sql" not in accepted_codes(result)
    assert "reporting" in accepted_codes(result)


def test_phrase_case_and_optional_case_sensitive_matching(
    cleaned_job_factory: Callable[..., CleanedJob], extraction_config
) -> None:
    profile, dictionary = extraction_config
    job = cleaned_job_factory(
        title_clean="power bi Analyst",
        description_text_clean="Use python and r for analysis; R is preferred.",
    )

    result = extract_job_evidence(job, profile, dictionary)
    codes = accepted_codes(result)

    assert "power_bi" in codes
    assert "python" in codes
    assert codes.count("r") == 1


def test_sql_server_longest_match_suppresses_nested_sql(
    cleaned_job_factory: Callable[..., CleanedJob], extraction_config
) -> None:
    profile, dictionary = extraction_config
    job = cleaned_job_factory(
        title_clean="SQL Server Analyst",
        description_text_clean="Maintain a fictional warehouse.",
    )

    result = extract_job_evidence(job, profile, dictionary)

    assert accepted_codes(result) == ["sql_server"]


def test_repeated_mentions_and_sections_preserve_separate_evidence(
    cleaned_job_factory: Callable[..., CleanedJob], extraction_config
) -> None:
    profile, dictionary = extraction_config
    job = cleaned_job_factory(
        title_clean="SQL Analyst",
        summary_text_clean="SQL reporting",
        bullet_points_clean=("Use SQL", "Review SQL outputs"),
        description_text_clean="SQL supports the fictional service.",
    )

    result = extract_job_evidence(job, profile, dictionary)
    sql_rows = [row for row in result.evidence if row.requirement_code == "sql"]

    assert len(sql_rows) == 5
    assert {row.section_name for row in sql_rows} == {
        "title_clean",
        "summary_text_clean",
        "bullet_points_clean",
        "description_text_clean",
    }
    assert {row.section_weight for row in sql_rows} == {
        profile.section_weights[section] for section in profile.section_weights
    }


def test_non_content_fields_are_never_searched(
    cleaned_job_factory: Callable[..., CleanedJob], extraction_config
) -> None:
    profile, dictionary = extraction_config
    job = cleaned_job_factory(
        job_url="https://python.example.test/jobs/sql",
        company_name_clean="Power BI Python SQL Pty Ltd",
        title_clean="General Analyst",
        description_text_clean="Build fictional outputs.",
        quality_flags=("requires_tableau_review",),
    )

    result = extract_job_evidence(job, profile, dictionary)

    assert result.evidence == ()


@pytest.mark.parametrize(
    "text",
    [
        "No SQL experience required for this fictional role.",
        "Python is not required for this fictional role.",
        "Complete the task without using Power BI.",
    ],
)
def test_negative_context_is_retained_as_suppressed_evidence(
    cleaned_job_factory: Callable[..., CleanedJob], extraction_config, text: str
) -> None:
    profile, dictionary = extraction_config
    job = cleaned_job_factory(
        title_clean="General Analyst", description_text_clean=text
    )

    result = extract_job_evidence(job, profile, dictionary)

    assert result.suppressed_negative_context_count == 1
    assert accepted_codes(result) == []
    assert result.evidence[0].evidence_status == "suppressed_negative_context"
    assert result.evidence[0].evidence_score == 0


def test_evidence_offsets_text_snippet_and_redaction_are_deterministic(
    cleaned_job_factory: Callable[..., CleanedJob], extraction_config
) -> None:
    profile, dictionary = extraction_config
    text = (
        "Contact private@example.test or 0412 345 678. "
        "Use Python for a fictional reporting task. " + "Context " * 30
    )
    job = cleaned_job_factory(
        title_clean="General Analyst", description_text_clean=text
    )

    first = extract_job_evidence(job, profile, dictionary)
    second = extract_job_evidence(job, profile, dictionary)
    evidence = next(row for row in first.evidence if row.requirement_code == "python")

    assert evidence.matched_text == "Python"
    assert text[evidence.evidence_start : evidence.evidence_end] == "Python"
    assert "[[Python]]" in evidence.evidence_snippet
    assert len(evidence.evidence_snippet) <= profile.evidence_snippet_length
    assert "private@example.test" not in evidence.evidence_snippet
    assert "0412 345 678" not in evidence.evidence_snippet
    assert first == second
