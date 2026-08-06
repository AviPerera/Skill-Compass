"""Define typed job records shared by mapping and cleaning layers.

These application contracts are source-independent after mapping and must not
open files, apply business transformations, or depend on database technology.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

# =============================================================================
# Shared immutable model configuration
# =============================================================================


class ImmutableModel(BaseModel):
    """Provide strict immutable behaviour for application contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# =============================================================================
# Canonical mapping contracts
# =============================================================================


class MappedJob(ImmutableModel):
    """Represent one structurally valid source row in canonical mapped form."""

    source_code: str
    source_job_id: str
    job_url: str
    source_row_number: int
    mapping_version: str
    mapping_config_hash: str
    canonical_schema_version: str
    scraped_at_raw: str | None = None

    title_raw: str
    company_name_raw: str | None = None
    advertiser_name_raw: str | None = None
    employer_name_raw: str | None = None
    summary_text_raw: str | None = None
    bullet_points_raw: tuple[str, ...] = ()
    description_html_raw: str | None = None
    description_text_raw: str | None = None

    source_role_code_raw: str | None = None
    classification_raw: str | None = None
    classification_code_raw: str | None = None
    subclassification_raw: str | None = None
    subclassification_code_raw: str | None = None

    location_raw: str | None = None
    location_long_raw: str | None = None
    country_raw: str | None = None
    country_code_raw: str | None = None
    area_hierarchy_raw: tuple[str, ...] = ()

    work_type_raw: str | None = None
    work_types_raw: tuple[str, ...] = ()
    work_arrangement_raw: str | None = None
    is_remote_raw: bool | None = None

    salary_label_raw: str | None = None
    salary_min_raw: Decimal | None = None
    salary_max_raw: Decimal | None = None
    salary_currency_raw: str | None = None
    salary_period_raw: str | None = None

    listing_date_raw: str | None = None
    expires_at_raw: str | None = None
    is_expired_raw: bool | None = None
    is_featured_raw: bool | None = None

    mapping_status: Literal["mapped"] = "mapped"
    fallback_fields_used: tuple[str, ...] = ()
    mapping_quality_flags: tuple[str, ...] = ()
    usable_description_status: Literal["usable", "missing"]
    analytically_eligible: bool


RejectionReasonCode = Literal[
    "missing_source_job_id",
    "missing_title",
    "missing_job_url",
    "invalid_source_job_id",
    "invalid_job_url",
    "mapping_configuration_error",
    "mapped_record_validation_error",
    "duplicate_same_content",
    "duplicate_conflicting_content",
]


class RejectedRecord(ImmutableModel):
    """Represent a rejected row using only safe diagnostic fields."""

    source_row_number: int
    source_code: str
    source_job_id: str | None = None
    title_raw: str | None = None
    rejection_stage: Literal["mapping", "deduplication", "cleaning"]
    rejection_reason_code: RejectionReasonCode
    rejection_reason_detail: str
    mapping_version: str
    canonical_schema_version: str


# =============================================================================
# Deterministic cleaning contract
# =============================================================================


class CleanedJob(ImmutableModel):
    """Represent one deduplicated mapped job after deterministic cleaning."""

    source_code: str
    source_job_id: str
    job_url: str
    source_row_number: int
    mapping_version: str
    mapping_config_hash: str
    canonical_schema_version: str
    content_hash: str

    title_raw: str
    title_clean: str
    company_name_raw: str | None = None
    company_name_clean: str | None = None
    summary_text_clean: str | None = None
    bullet_points_clean: tuple[str, ...] = ()
    description_text_clean: str | None = None
    usable_description_status: Literal["usable", "missing"]
    analytically_eligible: bool

    source_role_code_raw: str | None = None
    classification_raw: str | None = None
    classification_code_raw: str | None = None
    subclassification_raw: str | None = None
    subclassification_code_raw: str | None = None

    location_raw: str | None = None
    country_code: str | None = None
    state_code: str | None = None
    state_name: str | None = None
    city_name: str | None = None
    suburb_name: str | None = None
    geography_parse_method: str
    geography_parse_status: str

    salary_label_raw: str | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    salary_parse_method: str
    salary_parse_status: str

    employment_type_codes: tuple[str, ...]
    employment_parse_status: str
    work_mode_code: str
    work_mode_parse_method: str
    work_mode_parse_status: str

    listing_date: date | None = None
    listing_date_parse_method: str
    listing_date_parse_status: str
    expires_at: datetime | None = None
    expires_at_parse_status: str
    scraped_at: datetime | None = None

    quality_flags: tuple[str, ...] = ()
    fallback_fields_used: tuple[str, ...] = ()
    cleaning_status: Literal["cleaned", "cleaned_with_flags"]
