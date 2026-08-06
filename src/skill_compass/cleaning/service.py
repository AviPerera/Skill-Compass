"""Coordinate source-independent deterministic cleaning for one mapped job.

This cleaning-layer service composes focused cleaners and must not read or
write CSV files, deduplicate identities, or implement later classification.
"""

from __future__ import annotations

from skill_compass.cleaning.dates import parse_listing_date, parse_timestamp
from skill_compass.cleaning.employment import normalize_employment_types
from skill_compass.cleaning.geography import normalize_geography
from skill_compass.cleaning.hashing import calculate_content_hash
from skill_compass.cleaning.html import html_to_text
from skill_compass.cleaning.organisation import clean_company_name
from skill_compass.cleaning.salary import normalize_salary
from skill_compass.cleaning.text import normalize_text
from skill_compass.cleaning.title import clean_title
from skill_compass.cleaning.work_mode import normalize_work_mode
from skill_compass.schemas.jobs import CleanedJob, MappedJob

# =============================================================================
# Public deterministic cleaning service
# =============================================================================


def clean_mapped_job(mapped_job: MappedJob) -> CleanedJob:
    """Clean one typed mapped job and calculate its process-relevant content hash."""
    title_clean = clean_title(mapped_job.title_raw)
    company_name_clean = clean_company_name(mapped_job.company_name_raw)
    summary_text_clean = normalize_text(mapped_job.summary_text_raw)
    bullet_points_clean = tuple(
        cleaned
        for point in mapped_job.bullet_points_raw
        if (cleaned := normalize_text(point)) is not None
    )
    description_text_clean = normalize_text(mapped_job.description_text_raw)
    if description_text_clean is None:
        description_text_clean = html_to_text(mapped_job.description_html_raw)

    listing_date = parse_listing_date(
        mapped_job.listing_date_raw, mapped_job.scraped_at_raw
    )
    expires_at = parse_timestamp(mapped_job.expires_at_raw)
    scraped_at = parse_timestamp(mapped_job.scraped_at_raw)
    geography = normalize_geography(
        location_raw=mapped_job.location_raw,
        location_long_raw=mapped_job.location_long_raw,
        country_raw=mapped_job.country_raw,
        country_code_raw=mapped_job.country_code_raw,
        area_hierarchy_raw=mapped_job.area_hierarchy_raw,
    )
    salary = normalize_salary(
        minimum_raw=mapped_job.salary_min_raw,
        maximum_raw=mapped_job.salary_max_raw,
        currency_raw=mapped_job.salary_currency_raw,
        period_raw=mapped_job.salary_period_raw,
        label_raw=mapped_job.salary_label_raw,
    )
    employment = normalize_employment_types(
        mapped_job.work_type_raw, mapped_job.work_types_raw
    )
    work_mode = normalize_work_mode(
        mapped_job.work_arrangement_raw, mapped_job.is_remote_raw
    )

    quality_flags = set(mapped_job.mapping_quality_flags)
    quality_flags.update(work_mode.quality_flags)
    if geography.status in {"missing", "unknown"}:
        quality_flags.add("geography_unknown")
    if salary.status == "unknown":
        quality_flags.add("salary_unknown")
    elif salary.status == "invalid_range":
        quality_flags.add("salary_invalid_range")
    if listing_date.status == "unparseable":
        quality_flags.add("listing_date_unparseable")
    if employment.status in {"unknown", "partial"}:
        quality_flags.add("employment_type_unknown")
    if work_mode.status == "unknown":
        quality_flags.add("work_mode_unknown")

    content_fields: dict[str, object] = {
        "source_code": mapped_job.source_code,
        "source_job_id": mapped_job.source_job_id,
        "job_url": mapped_job.job_url,
        "title_clean": title_clean,
        "company_name_clean": company_name_clean,
        "summary_text_clean": summary_text_clean,
        "bullet_points_clean": bullet_points_clean,
        "description_text_clean": description_text_clean,
        "source_role_code_raw": mapped_job.source_role_code_raw,
        "classification_raw": mapped_job.classification_raw,
        "classification_code_raw": mapped_job.classification_code_raw,
        "subclassification_raw": mapped_job.subclassification_raw,
        "subclassification_code_raw": mapped_job.subclassification_code_raw,
        "country_code": geography.country_code,
        "state_code": geography.state_code,
        "city_name": geography.city_name,
        "suburb_name": geography.suburb_name,
        "salary_min": salary.minimum,
        "salary_max": salary.maximum,
        "salary_currency": salary.currency,
        "salary_period": salary.period,
        "employment_type_codes": employment.codes,
        "work_mode_code": work_mode.code,
        "listing_date": listing_date.value,
    }
    content_hash = calculate_content_hash(content_fields)
    ordered_flags = tuple(sorted(quality_flags))

    return CleanedJob(
        source_code=mapped_job.source_code,
        source_job_id=mapped_job.source_job_id,
        job_url=mapped_job.job_url,
        source_row_number=mapped_job.source_row_number,
        mapping_version=mapped_job.mapping_version,
        mapping_config_hash=mapped_job.mapping_config_hash,
        canonical_schema_version=mapped_job.canonical_schema_version,
        content_hash=content_hash,
        title_raw=mapped_job.title_raw,
        title_clean=title_clean,
        company_name_raw=mapped_job.company_name_raw,
        company_name_clean=company_name_clean,
        summary_text_clean=summary_text_clean,
        bullet_points_clean=bullet_points_clean,
        description_text_clean=description_text_clean,
        usable_description_status=mapped_job.usable_description_status,
        analytically_eligible=mapped_job.analytically_eligible,
        source_role_code_raw=mapped_job.source_role_code_raw,
        classification_raw=mapped_job.classification_raw,
        classification_code_raw=mapped_job.classification_code_raw,
        subclassification_raw=mapped_job.subclassification_raw,
        subclassification_code_raw=mapped_job.subclassification_code_raw,
        location_raw=mapped_job.location_raw,
        country_code=geography.country_code,
        state_code=geography.state_code,
        state_name=geography.state_name,
        city_name=geography.city_name,
        suburb_name=geography.suburb_name,
        geography_parse_method=geography.method,
        geography_parse_status=geography.status,
        salary_label_raw=mapped_job.salary_label_raw,
        salary_min=salary.minimum,
        salary_max=salary.maximum,
        salary_currency=salary.currency,
        salary_period=salary.period,
        salary_parse_method=salary.method,
        salary_parse_status=salary.status,
        employment_type_codes=employment.codes,
        employment_parse_status=employment.status,
        work_mode_code=work_mode.code,
        work_mode_parse_method=work_mode.method,
        work_mode_parse_status=work_mode.status,
        listing_date=listing_date.value,
        listing_date_parse_method=listing_date.method,
        listing_date_parse_status=listing_date.status,
        expires_at=expires_at.value,
        expires_at_parse_status=expires_at.status,
        scraped_at=scraped_at.value,
        quality_flags=ordered_flags,
        fallback_fields_used=mapped_job.fallback_fields_used,
        cleaning_status="cleaned_with_flags" if ordered_flags else "cleaned",
    )
