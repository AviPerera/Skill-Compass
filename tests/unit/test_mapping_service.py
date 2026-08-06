"""Test deterministic source precedence and safe structural row rejection."""

from pathlib import Path

import pytest

from skill_compass.mapping.config import SourceMappingConfig, load_mapping_config
from skill_compass.mapping.service import map_source_row

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = PROJECT_ROOT / "sources/apify_seek_current/source_mapping.yaml"


@pytest.fixture
def mapping() -> SourceMappingConfig:
    """Load the repository mapping contract for focused behaviour tests."""
    return load_mapping_config(MAPPING_PATH)


def valid_source_row() -> dict[str, str]:
    """Return one small fictional row containing preferred and fallback fields."""
    return {
        "id": "preferred-100",
        "raw/detail/id": "fallback-100",
        "title": "Data Analyst",
        "raw/detail/title": "Fallback Analyst",
        "job_url": "https://example.test/jobs/preferred-100",
        "company_name": "Example Company",
        "advertiser_name": "Example Advertiser",
        "description_html": (
            "<p>Fictional description. Contact private@example.test or "
            "0000000000 using fixture-token.</p>"
        ),
        "contact_email": "private@example.test",
        "contact_phone": "0000000000",
        "raw/listing/solMetadata/searchRequestToken": "fixture-token",
        "raw/listing/tracking": "fixture-tracking",
    }


def test_preferred_field_wins_and_source_code_comes_from_config(
    mapping: SourceMappingConfig,
) -> None:
    outcome = map_source_row(valid_source_row(), mapping, source_row_number=1)

    assert outcome.rejected_record is None
    assert outcome.mapped_job is not None
    assert outcome.mapped_job.source_job_id == "preferred-100"
    assert outcome.mapped_job.title_raw == "Data Analyst"
    assert outcome.mapped_job.source_code == "apify_seek_current"
    assert outcome.mapped_job.fallback_fields_used == ()


def test_whitespace_preferred_value_uses_ordered_fallback(
    mapping: SourceMappingConfig,
) -> None:
    row = valid_source_row()
    row["id"] = "   "
    row["title"] = "\t"

    outcome = map_source_row(row, mapping, source_row_number=2)

    assert outcome.mapped_job is not None
    assert outcome.mapped_job.source_job_id == "fallback-100"
    assert outcome.mapped_job.title_raw == "Fallback Analyst"
    assert outcome.mapped_job.fallback_fields_used == (
        "source_job_id:raw/detail/id",
        "title_raw:raw/detail/title",
    )


@pytest.mark.parametrize(
    ("field", "reason_code"),
    [
        ("id", "missing_source_job_id"),
        ("title", "missing_title"),
        ("job_url", "missing_job_url"),
    ],
)
def test_missing_required_field_creates_safe_rejection(
    mapping: SourceMappingConfig,
    field: str,
    reason_code: str,
) -> None:
    row = valid_source_row()
    row[field] = " "
    if field == "id":
        row["raw/detail/id"] = ""
    if field == "title":
        row["raw/detail/title"] = ""

    outcome = map_source_row(row, mapping, source_row_number=3)

    assert outcome.mapped_job is None
    assert outcome.rejected_record is not None
    assert outcome.rejected_record.rejection_reason_code == reason_code
    assert "Fictional description" not in outcome.rejected_record.model_dump_json()
    assert "fixture-token" not in outcome.rejected_record.model_dump_json()


def test_invalid_job_url_is_rejected(mapping: SourceMappingConfig) -> None:
    row = valid_source_row()
    row["job_url"] = "not-an-absolute-url"

    outcome = map_source_row(row, mapping, source_row_number=4)

    assert outcome.rejected_record is not None
    assert outcome.rejected_record.rejection_reason_code == "invalid_job_url"


def test_invalid_source_job_id_is_rejected(mapping: SourceMappingConfig) -> None:
    row = valid_source_row()
    row["id"] = "invalid\x00identifier"

    outcome = map_source_row(row, mapping, source_row_number=5)

    assert outcome.rejected_record is not None
    assert outcome.rejected_record.rejection_reason_code == "invalid_source_job_id"


def test_contact_and_tracking_fields_do_not_enter_mapped_output(
    mapping: SourceMappingConfig,
) -> None:
    outcome = map_source_row(valid_source_row(), mapping, source_row_number=6)

    assert outcome.mapped_job is not None
    serialized = outcome.mapped_job.model_dump_json()
    assert "private@example.test" not in serialized
    assert "0000000000" not in serialized
    assert "fixture-token" not in serialized
    assert "fixture-tracking" not in serialized
    assert "[redacted" in serialized


def test_missing_description_is_retained_with_quality_status(
    mapping: SourceMappingConfig,
) -> None:
    row = valid_source_row()
    row["description_html"] = ""

    outcome = map_source_row(row, mapping, source_row_number=7)

    assert outcome.rejected_record is None
    assert outcome.mapped_job is not None
    assert outcome.mapped_job.usable_description_status == "missing"
    assert outcome.mapped_job.analytically_eligible is False
    assert "missing_usable_description" in outcome.mapped_job.mapping_quality_flags


def test_advertiser_is_not_used_as_company_fallback(
    mapping: SourceMappingConfig,
) -> None:
    row = valid_source_row()
    row["company_name"] = ""
    row["raw/listing/companyName"] = ""

    outcome = map_source_row(row, mapping, source_row_number=8)

    assert outcome.mapped_job is not None
    assert outcome.mapped_job.company_name_raw is None
    assert outcome.mapped_job.advertiser_name_raw == "Example Advertiser"
    assert "missing_company" in outcome.mapped_job.mapping_quality_flags
