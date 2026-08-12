"""Define typed contracts for deterministic requirement extraction.

These application-layer records are storage-neutral and must not read files,
render charts, persist database rows, or implement matching algorithms.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from skill_compass.schemas.jobs import ImmutableModel

# =============================================================================
# Configuration contracts
# =============================================================================


class ConfidenceThresholds(ImmutableModel):
    """Define minimum deterministic scores for stable confidence labels."""

    high_min: Decimal = Field(ge=0, le=1)
    medium_min: Decimal = Field(ge=0, le=1)
    low_min: Decimal = Field(ge=0, le=1)


class MinimumEligibilityRules(ImmutableModel):
    """Define the cleaned-job eligibility gate used before extraction."""

    require_analytically_eligible: bool = True
    require_usable_description: bool = True


class ExtractionProfile(ImmutableModel):
    """Represent one validated and hashed extraction profile."""

    profile_code: str
    profile_name: str
    profile_version: str
    requirement_dictionary_version: str
    extractor_version: str
    extraction_output_schema_version: str
    supported_requirement_types: tuple[str, ...]
    section_weights: dict[str, Decimal]
    confidence_thresholds: ConfidenceThresholds
    evidence_snippet_length: int = Field(ge=80, le=300)
    negative_context_window: int = Field(ge=10, le=120)
    minimum_analytical_eligibility: MinimumEligibilityRules
    active: bool
    profile_hash: str


class RequirementAlias(ImmutableModel):
    """Represent one validated active alias from the requirement dictionary."""

    requirement_code: str
    requirement_name: str
    requirement_type: str
    category_code: str
    category_name: str
    dashboard_group: str
    alias_text: str
    match_type: Literal["token", "phrase", "exact"]
    case_sensitive: bool
    require_word_boundary: bool
    negative_context_terms: tuple[str, ...] = ()
    active: bool
    sort_order: int = Field(ge=1)
    dictionary_version: str
    notes: str | None = None


class RequirementDefinition(ImmutableModel):
    """Represent one canonical requirement with its ordered active aliases."""

    requirement_code: str
    requirement_name: str
    requirement_type: str
    category_code: str
    category_name: str
    dashboard_group: str
    sort_order: int = Field(ge=1)
    dictionary_version: str
    aliases: tuple[RequirementAlias, ...]


class RequirementDictionary(ImmutableModel):
    """Represent a validated, versioned collection of active requirements."""

    dictionary_version: str
    dictionary_hash: str
    requirements: tuple[RequirementDefinition, ...]
    active_aliases: tuple[RequirementAlias, ...]
    category_codes: tuple[str, ...]


# =============================================================================
# Evidence and aggregate contracts
# =============================================================================


EvidenceStatus = Literal["accepted", "review", "suppressed_negative_context"]
ConfidenceLevel = Literal["high", "medium", "low", "review"]


class RequirementEvidence(ImmutableModel):
    """Preserve one bounded, explainable alias occurrence in a content section."""

    source_code: str
    source_job_id: str
    requirement_code: str
    requirement_name: str
    requirement_type: str
    category_code: str
    alias_text: str
    matched_text: str
    section_name: str
    section_weight: Decimal = Field(ge=0, le=1)
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(ge=0)
    evidence_snippet: str
    match_type: Literal["token", "phrase", "exact"]
    evidence_score: Decimal = Field(ge=0, le=1)
    dictionary_version: str
    dictionary_hash: str
    profile_version: str
    profile_hash: str
    extractor_version: str
    extractor_config_hash: str
    extraction_output_schema_version: str
    evidence_status: EvidenceStatus


class JobRequirementMatch(ImmutableModel):
    """Aggregate accepted evidence to one job and canonical requirement row."""

    source_code: str
    source_job_id: str
    requirement_code: str
    requirement_name: str
    requirement_type: str
    category_code: str
    category_name: str
    dashboard_group: str
    evidence_count: int = Field(ge=1)
    matched_sections: tuple[str, ...]
    matched_aliases: tuple[str, ...]
    highest_section_weight: Decimal = Field(ge=0, le=1)
    extraction_score: Decimal = Field(ge=0, le=1)
    confidence_level: ConfidenceLevel
    extraction_method: Literal["deterministic_dictionary"]
    dictionary_version: str
    dictionary_hash: str
    extractor_version: str
    profile_version: str
    extraction_output_schema_version: str
    quality_flags: tuple[str, ...] = ()


ExtractionStatus = Literal[
    "extracted",
    "no_requirements_detected",
    "skipped_ineligible",
    "review_required",
    "processing_error",
]


class JobExtractionSummary(ImmutableModel):
    """Summarize deterministic extraction status and counts for one cleaned job."""

    source_code: str
    source_job_id: str
    analytically_eligible: bool
    extraction_status: ExtractionStatus
    distinct_requirement_count: int = Field(ge=0)
    distinct_skill_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    high_confidence_count: int = Field(ge=0)
    medium_confidence_count: int = Field(ge=0)
    low_confidence_count: int = Field(ge=0)
    review_count: int = Field(ge=0)
    category_count: int = Field(ge=0)
    extraction_quality_flags: tuple[str, ...] = ()
    dictionary_version: str
    extractor_version: str


class SkillDemandSummary(ImmutableModel):
    """Summarize distinct eligible-job demand for one active skill requirement."""

    requirement_code: str
    requirement_name: str
    category_code: str
    category_name: str
    dashboard_group: str
    eligible_job_count: int = Field(ge=0)
    matched_job_count: int = Field(ge=0)
    demand_rate: Decimal = Field(ge=0, le=1)
    total_evidence_count: int = Field(ge=0)
    high_confidence_job_count: int = Field(ge=0)
    medium_confidence_job_count: int = Field(ge=0)
    low_confidence_job_count: int = Field(ge=0)
    review_job_count: int = Field(ge=0)
    rank_overall: int = Field(ge=1)
    dictionary_version: str
    extractor_version: str
    extraction_output_schema_version: str


class ExtractionQualityMetric(ImmutableModel):
    """Represent one stable tabular extraction quality or reconciliation metric."""

    metric_category: str
    metric_name: str
    metric_value: str
    metric_status: Literal["pass", "fail", "warning", "info"]
    metric_detail: str


class ExtractionProcessingError(ImmutableModel):
    """Describe one controlled per-job processing error without private text."""

    source_code: str
    source_job_id: str
    error_code: str
    error_detail: str


class ExtractionRunResult(ImmutableModel):
    """Return all typed records and reconciliation evidence for one extraction run."""

    profile: ExtractionProfile
    requirement_dictionary: RequirementDictionary
    extractor_config_hash: str
    input_cleaned_jobs: int
    analytically_eligible_jobs: int
    analytically_ineligible_jobs: int
    processed_jobs: int
    skipped_jobs: int
    processing_error_jobs: int
    evidence: tuple[RequirementEvidence, ...]
    job_requirement_matches: tuple[JobRequirementMatch, ...]
    job_summaries: tuple[JobExtractionSummary, ...]
    skill_demand: tuple[SkillDemandSummary, ...]
    quality_metrics: tuple[ExtractionQualityMetric, ...]
    processing_errors: tuple[ExtractionProcessingError, ...]
    suppressed_negative_context_count: int
    reconciliation_passed: bool
