"""Define typed contracts for explainable role classification.

These application-layer records are storage-neutral and must not read files,
render charts, classify seniority, or implement profile-relevance decisions.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from skill_compass.schemas.jobs import ImmutableModel

# =============================================================================
# Governed role-rule configuration
# =============================================================================


class RoleScoringWeights(ImmutableModel):
    """Define bounded deterministic contributions for each evidence type."""

    strong_title: Decimal = Field(ge=0, le=1)
    supporting_title: Decimal = Field(ge=0, le=1)
    context_term: Decimal = Field(ge=0, le=1)
    source_hint: Decimal = Field(ge=0, le=1)
    conflicting_title: Decimal = Field(ge=0, le=1)
    exclusion_title: Decimal = Field(ge=0, le=1)


class RoleDecisionThresholds(ImmutableModel):
    """Define classification, ambiguity, and confidence cut-offs."""

    minimum_classification_score: Decimal = Field(ge=0, le=1)
    meaningful_evidence_score: Decimal = Field(ge=0, le=1)
    ambiguity_margin: Decimal = Field(ge=0, le=1)
    high_confidence_min: Decimal = Field(ge=0, le=1)
    medium_confidence_min: Decimal = Field(ge=0, le=1)


class RoleRule(ImmutableModel):
    """Represent one governed analytical role and its evidence vocabulary."""

    role_group_code: str
    role_group_label: str
    sort_order: int = Field(ge=1)
    strong_title_terms: tuple[str, ...]
    supporting_title_terms: tuple[str, ...] = ()
    context_terms: tuple[str, ...]
    source_hint_terms: tuple[str, ...] = ()
    conflicting_title_terms: tuple[str, ...] = ()
    exclusion_title_terms: tuple[str, ...] = ()


class RoleRuleSet(ImmutableModel):
    """Represent one validated and reproducibly hashed role-rule document."""

    profile_code: str
    role_classifier_version: str
    role_rules_version: str
    role_output_schema_version: str
    weights: RoleScoringWeights
    thresholds: RoleDecisionThresholds
    section_multipliers: dict[str, Decimal]
    max_context_terms_per_role: int = Field(ge=1, le=20)
    max_source_hints_per_role: int = Field(ge=1, le=10)
    evidence_term_max_length: int = Field(ge=20, le=120)
    review_evidence_max_length: int = Field(ge=80, le=1000)
    roles: tuple[RoleRule, ...]
    role_rules_hash: str


# =============================================================================
# Classification evidence and result contracts
# =============================================================================


EvidenceEffect = Literal["positive", "supporting", "conflicting"]
EvidenceType = Literal[
    "strong_title",
    "supporting_title",
    "context_term",
    "source_hint",
    "conflicting_title",
    "exclusion_title",
]
ConfidenceLevel = Literal["high", "medium", "low"]


class RoleClassificationEvidence(ImmutableModel):
    """Preserve one bounded rule match affecting one candidate role score."""

    source_code: str
    source_job_id: str
    role_group_code: str
    evidence_section: str
    evidence_term: str
    evidence_type: EvidenceType
    evidence_weight: Decimal = Field(ge=-1, le=1)
    evidence_effect: EvidenceEffect


class JobRoleClassification(ImmutableModel):
    """Represent one deterministic final role outcome and leading candidates."""

    source_code: str
    source_job_id: str
    role_group_code: str
    role_group_label: str
    role_confidence_score: Decimal = Field(ge=0, le=1)
    role_confidence_level: ConfidenceLevel
    role_review_flag: bool
    role_reason: str
    candidate_role_1_code: str | None = None
    candidate_role_1_score: Decimal | None = Field(default=None, ge=0, le=1)
    candidate_role_2_code: str | None = None
    candidate_role_2_score: Decimal | None = Field(default=None, ge=0, le=1)
    role_classifier_version: str
    role_rules_version: str
    role_rules_hash: str


class RoleDistributionSummary(ImmutableModel):
    """Summarize job counts and full-input shares by final role outcome."""

    role_group_code: str
    role_group_label: str
    job_count: int = Field(ge=0)
    job_share: Decimal = Field(ge=0, le=1)


class RoleClassificationQuality(ImmutableModel):
    """Store one reconciled, non-accuracy quality summary for a role run."""

    total_jobs_received: int = Field(ge=0)
    classified_into_dashboard_role: int = Field(ge=0)
    analytical_role_population: int = Field(ge=0)
    other_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    review_rate: Decimal = Field(ge=0, le=1)
    high_confidence_count: int = Field(ge=0)
    medium_confidence_count: int = Field(ge=0)
    low_confidence_count: int = Field(ge=0)
    missing_title_count: int = Field(ge=0)
    missing_description_count: int = Field(ge=0)
    reconciliation_status: Literal["pass", "fail"]
    denominator_definition: str


class RoleReviewQueueItem(ImmutableModel):
    """Expose only bounded fields needed to inspect a Review outcome."""

    source_code: str
    source_job_id: str
    title_clean: str
    candidate_role_1_code: str | None = None
    candidate_role_1_score: Decimal | None = Field(default=None, ge=0, le=1)
    candidate_role_2_code: str | None = None
    candidate_role_2_score: Decimal | None = Field(default=None, ge=0, le=1)
    role_reason: str
    bounded_evidence: str


class RoleClassificationRunResult(ImmutableModel):
    """Bundle all typed role outcomes and reconciliation evidence for one run."""

    rules: RoleRuleSet
    input_job_count: int = Field(ge=0)
    classifications: tuple[JobRoleClassification, ...]
    evidence: tuple[RoleClassificationEvidence, ...]
    distribution: tuple[RoleDistributionSummary, ...]
    quality: RoleClassificationQuality
    review_queue: tuple[RoleReviewQueueItem, ...]
    reconciliation_passed: bool
