"""Define typed channel-neutral analytical facts and aggregate contracts.

This schema module belongs to the reusable analytics boundary and must not read
files, render dashboard visuals, persist database rows, or contain Power BI
presentation logic.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from skill_compass.schemas.jobs import ImmutableModel

# =============================================================================
# Canonical analytical facts
# =============================================================================


class AnalyticsJobFact(ImmutableModel):
    """Represent one profile-included advertisement at canonical job grain."""

    source_code: str
    source_job_id: str
    content_hash: str
    title_clean: str
    state_code: str | None = None
    state_name: str | None = None
    city_name: str | None = None
    primary_employment_type_code: str
    work_mode_code: str
    role_group_code: str
    role_group_label: str
    role_confidence_score: Decimal = Field(ge=0, le=1)
    seniority_code: str
    seniority_label: str
    seniority_rank: int | None = Field(default=None, ge=1)
    graduate_level_flag: bool
    relevance_score: Decimal = Field(ge=0, le=1)
    distinct_skill_count: int = Field(ge=0)


class AnalyticsJobSkillFact(ImmutableModel):
    """Represent one included job and one canonical detected skill."""

    source_code: str
    source_job_id: str
    requirement_code: str
    requirement_name: str
    category_code: str
    category_name: str
    dashboard_group: str
    mention_count: int = Field(ge=1)
    weighted_match_score: Decimal = Field(ge=0, le=1)
    confidence_level: str


# =============================================================================
# Channel-neutral aggregate contracts
# =============================================================================


class SkillDemandMetric(ImmutableModel):
    """Store distinct-job demand for one governed skill."""

    requirement_code: str
    requirement_name: str
    category_code: str
    category_name: str
    dashboard_group: str
    supporting_job_count: int = Field(ge=0)
    eligible_job_count: int = Field(ge=0)
    demand_rate: Decimal = Field(ge=0, le=1)
    rank_overall: int = Field(ge=1)


class SkillRoleDemandMetric(ImmutableModel):
    """Store role-specific distinct-job demand for one governed skill."""

    role_group_code: str
    role_group_label: str
    role_sort_order: int = Field(ge=1)
    requirement_code: str
    requirement_name: str
    category_code: str
    dashboard_group: str
    supporting_job_count: int = Field(ge=0)
    eligible_job_count: int = Field(ge=0)
    demand_rate: Decimal = Field(ge=0, le=1)


class DistributionMetric(ImmutableModel):
    """Store one explicit-denominator categorical job distribution."""

    dimension_name: str
    dimension_code: str
    dimension_label: str
    sort_order: int = Field(ge=1)
    job_count: int = Field(ge=0)
    eligible_job_count: int = Field(ge=0)
    job_rate: Decimal = Field(ge=0, le=1)


class RoleSummaryMetric(ImmutableModel):
    """Store role volume, skill variety, and graduate-level availability."""

    role_group_code: str
    role_group_label: str
    sort_order: int = Field(ge=1)
    job_count: int = Field(ge=0)
    eligible_job_count: int = Field(ge=0)
    job_share: Decimal = Field(ge=0, le=1)
    average_distinct_skills: Decimal = Field(ge=0)
    graduate_level_count: int = Field(ge=0)
    graduate_level_rate: Decimal = Field(ge=0, le=1)


class RoleSeniorityMetric(ImmutableModel):
    """Store one role and governed seniority cross-tabulation cell."""

    role_group_code: str
    role_group_label: str
    role_sort_order: int = Field(ge=1)
    seniority_code: str
    seniority_label: str
    seniority_rank: int = Field(ge=1)
    job_count: int = Field(ge=0)
    role_job_count: int = Field(ge=0)
    role_rate: Decimal = Field(ge=0, le=1)


class SkillCombinationMetric(ImmutableModel):
    """Store one pair/triple combination for an explicit role/cohort scope."""

    scope_code: str
    scope_label: str
    graduate_friendly_flag: bool
    combination_size: Literal[2, 3]
    requirement_codes: tuple[str, ...]
    combination_label: str
    supporting_job_count: int = Field(ge=0)
    eligible_job_count: int = Field(ge=0)
    job_percentage: Decimal = Field(ge=0, le=1)
    support: Decimal = Field(ge=0, le=1)
    confidence: Decimal = Field(ge=0, le=1)
    lift: Decimal = Field(ge=0)
    combination_rank: int = Field(ge=1)
    sample_size_warning_flag: bool


class AnalyticsQualityMetric(ImmutableModel):
    """Record reconciliation or coverage evidence without private content."""

    metric_category: str
    metric_name: str
    metric_value: str
    metric_status: Literal["pass", "warning", "info"]
    metric_detail: str


# =============================================================================
# Complete in-memory run result
# =============================================================================


class AnalyticsRunResult(ImmutableModel):
    """Bundle facts, aggregates, combinations, and reconciliation evidence."""

    profile_code: str
    input_cleaned_job_count: int = Field(ge=0)
    classifier_input_job_count: int = Field(ge=0)
    included_job_count: int = Field(ge=0)
    excluded_job_count: int = Field(ge=0)
    review_job_count: int = Field(ge=0)
    job_facts: tuple[AnalyticsJobFact, ...]
    job_skill_facts: tuple[AnalyticsJobSkillFact, ...]
    skill_demand: tuple[SkillDemandMetric, ...]
    skill_role_demand: tuple[SkillRoleDemandMetric, ...]
    role_summary: tuple[RoleSummaryMetric, ...]
    role_seniority: tuple[RoleSeniorityMetric, ...]
    seniority_distribution: tuple[DistributionMetric, ...]
    state_distribution: tuple[DistributionMetric, ...]
    city_distribution: tuple[DistributionMetric, ...]
    employment_type_distribution: tuple[DistributionMetric, ...]
    work_mode_distribution: tuple[DistributionMetric, ...]
    skill_combinations: tuple[SkillCombinationMetric, ...]
    quality_metrics: tuple[AnalyticsQualityMetric, ...]
    reconciliation_passed: bool
