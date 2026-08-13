"""Test Feature 8 analytical input guards and denominator behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_compass.analytics.service import AnalyticsInputError, build_analytics
from skill_compass.classification.config import load_role_rules
from skill_compass.classification.seniority_config import load_seniority_rules
from skill_compass.extraction.dictionary import load_requirement_dictionary
from skill_compass.extraction.profile import load_extraction_profile
from skill_compass.schemas.classification import (
    JobProfileRelevance,
    JobRoleClassification,
    JobSeniorityClassification,
)

PROFILE_PATH = Path("profiles/data_analytics/profile.yaml")
DICTIONARY_PATH = Path("profiles/data_analytics/requirements.csv")
ROLE_RULES_PATH = Path("profiles/data_analytics/role_rules.yaml")
SENIORITY_RULES_PATH = Path("profiles/data_analytics/seniority_rules.yaml")


def _configuration() -> tuple[object, object, object]:
    """Load governed configuration shared by the small unit scenarios."""
    profile = load_extraction_profile(PROFILE_PATH)
    return (
        load_role_rules(ROLE_RULES_PATH),
        load_seniority_rules(SENIORITY_RULES_PATH),
        load_requirement_dictionary(DICTIONARY_PATH, profile),
    )


def test_duplicate_cleaned_identity_is_rejected(cleaned_job_factory: object) -> None:
    role_rules, seniority_rules, dictionary = _configuration()
    build = cleaned_job_factory
    job = build(source_job_id="fixture-duplicate")
    role = JobRoleClassification(
        source_code=job.source_code,
        source_job_id=job.source_job_id,
        role_group_code="data_analyst",
        role_group_label="Data Analyst",
        role_confidence_score="0.8",
        role_confidence_level="high",
        role_review_flag=False,
        role_reason="Fictional governed evidence.",
        role_classifier_version="0.1.0",
        role_rules_version="0.1.0",
        role_rules_hash="a" * 64,
    )
    seniority = JobSeniorityClassification(
        source_code=job.source_code,
        source_job_id=job.source_job_id,
        seniority_code="junior",
        seniority_label="Junior",
        seniority_rank=2,
        graduate_level_flag=True,
        seniority_confidence_score="0.8",
        seniority_confidence_level="high",
        seniority_review_flag=False,
        seniority_conflict_flag=False,
        seniority_reason="Fictional governed evidence.",
        seniority_classifier_version="0.1.0",
        seniority_rules_version="0.1.0",
        seniority_rules_hash="b" * 64,
    )
    relevance = JobProfileRelevance(
        source_code=job.source_code,
        source_job_id=job.source_job_id,
        profile_code="data_analytics",
        relevance_status="included",
        relevance_score="0.8",
        relevance_review_flag=False,
        relevance_reason_code="direct_multi_source_inclusion",
        relevance_reason="Fictional governed evidence.",
        relevance_classifier_version="0.1.0",
        relevance_rules_version="0.1.0",
        relevance_rules_hash="c" * 64,
        positive_evidence_count=1,
        negative_evidence_count=0,
        evidence_family_count=1,
        classified_at="2026-08-13T00:00:00Z",
    )

    with pytest.raises(AnalyticsInputError, match="duplicate cleaned job"):
        build_analytics(
            cleaned_jobs=(job, job),
            role_classifications=(role,),
            seniority_classifications=(seniority,),
            relevance_classifications=(relevance,),
            requirement_matches=(),
            role_rules=role_rules,
            seniority_rules=seniority_rules,
            requirement_dictionary=dictionary,
        )
