"""Provide small fictional typed records for deterministic extraction tests.

These test helpers create sanitised application records and must not read the
private demonstration dataset or encode production classification labels.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from skill_compass.schemas.jobs import CleanedJob


@pytest.fixture
def cleaned_job_factory() -> Callable[..., CleanedJob]:
    """Return a factory for minimal fictional cleaned jobs."""

    def build_cleaned_job(**overrides: object) -> CleanedJob:
        values: dict[str, object] = {
            "source_code": "fixture_source",
            "source_job_id": "fixture-100",
            "job_url": "https://example.test/jobs/fixture-100",
            "source_row_number": 1,
            "mapping_version": "0.1.0",
            "mapping_config_hash": "a" * 64,
            "canonical_schema_version": "0.1.0",
            "content_hash": "b" * 64,
            "title_raw": "Data Analyst",
            "title_clean": "Data Analyst",
            "summary_text_clean": None,
            "bullet_points_clean": (),
            "description_text_clean": "Build fictional analytics outputs.",
            "usable_description_status": "usable",
            "analytically_eligible": True,
            "geography_parse_method": "australian_text",
            "geography_parse_status": "parsed",
            "salary_parse_method": "none",
            "salary_parse_status": "unknown",
            "employment_type_codes": ("full_time",),
            "employment_parse_status": "known",
            "work_mode_code": "hybrid",
            "work_mode_parse_method": "structured",
            "work_mode_parse_status": "known",
            "listing_date_parse_method": "none",
            "listing_date_parse_status": "missing",
            "expires_at_parse_status": "missing",
            "quality_flags": (),
            "fallback_fields_used": (),
            "cleaning_status": "cleaned",
        }
        values.update(overrides)
        return CleanedJob.model_validate(values)

    return build_cleaned_job
