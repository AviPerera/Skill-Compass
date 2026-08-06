"""Test deterministic content hashing and first-valid-row duplicate handling."""

from skill_compass.cleaning.hashing import calculate_content_hash
from skill_compass.mapping.deduplication import deduplicate_mapped_jobs
from skill_compass.schemas.jobs import MappedJob


def mapped_job(source_row_number: int, title: str = "Data Analyst") -> MappedJob:
    """Build a minimal fictional mapped job for duplicate tests."""
    return MappedJob(
        source_code="fixture_source",
        source_job_id="job-100",
        job_url="https://example.test/jobs/job-100",
        source_row_number=source_row_number,
        mapping_version="0.1.0",
        mapping_config_hash="a" * 64,
        canonical_schema_version="0.1.0",
        scraped_at_raw=f"2026-07-{20 + source_row_number:02d}T12:00:00+09:30",
        title_raw=title,
        description_html_raw="<p>Fictional description.</p>",
        usable_description_status="usable",
        analytically_eligible=True,
    )


def test_content_hash_is_deterministic_and_order_independent() -> None:
    first = calculate_content_hash({"title": "Data Analyst", "codes": ("a", "b")})
    reordered = calculate_content_hash({"codes": ("a", "b"), "title": "Data Analyst"})
    changed = calculate_content_hash(
        {"title": "Senior Data Analyst", "codes": ("a", "b")}
    )

    assert first == reordered
    assert first != changed


def test_first_valid_row_survives_same_and_conflicting_duplicates() -> None:
    first = mapped_job(1)
    same_content = mapped_job(2)
    conflicting_content = mapped_job(3, title="Senior Data Analyst")

    result = deduplicate_mapped_jobs((conflicting_content, same_content, first))

    assert result.survivors == (first,)
    assert result.duplicate_identity_count == 1
    assert result.duplicate_same_content_rows == 1
    assert result.duplicate_conflicting_content_rows == 1
    assert [rejection.rejection_reason_code for rejection in result.rejections] == [
        "duplicate_same_content",
        "duplicate_conflicting_content",
    ]
