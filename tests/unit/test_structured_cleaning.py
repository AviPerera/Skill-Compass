"""Test deterministic date, geography, salary, employment, and work-mode rules."""

from datetime import date
from decimal import Decimal

import pytest

from skill_compass.cleaning.dates import parse_listing_date
from skill_compass.cleaning.employment import normalize_employment_types
from skill_compass.cleaning.geography import normalize_geography
from skill_compass.cleaning.salary import normalize_salary
from skill_compass.cleaning.work_mode import normalize_work_mode


def test_absolute_and_relative_dates_use_explicit_sources() -> None:
    absolute = parse_listing_date("20/07/2026", None)
    relative = parse_listing_date("2 days ago", "2026-07-21T12:00:00+09:30")

    assert absolute.value == date(2026, 7, 20)
    assert absolute.method == "australian_numeric"
    assert relative.value == date(2026, 7, 19)
    assert relative.method == "relative_to_scraped_at"


def test_relative_date_without_reference_and_unknown_date_are_explicit() -> None:
    no_reference = parse_listing_date("2 days ago", None)
    malformed = parse_listing_date("not-a-date", "2026-07-21T12:00:00+09:30")

    assert no_reference.status == "unparseable"
    assert no_reference.method == "relative_without_reference"
    assert malformed.status == "unparseable"


def test_australian_geography_parses_adelaide_and_suburb_evidence() -> None:
    result = normalize_geography(
        location_raw="Norwood SA 5067",
        location_long_raw=None,
        country_raw="Australia",
        country_code_raw="AU",
        area_hierarchy_raw=("Adelaide", "South Australia"),
    )

    assert result.country_code == "AU"
    assert result.state_code == "SA"
    assert result.state_name == "South Australia"
    assert result.city_name == "Adelaide"
    assert result.suburb_name == "Norwood"
    assert result.status == "parsed"


def test_unknown_geography_remains_explicit() -> None:
    result = normalize_geography(
        location_raw="Mystery Region",
        location_long_raw=None,
        country_raw="Australia",
        country_code_raw="AU",
        area_hierarchy_raw=(),
    )

    assert result.city_name is None
    assert result.state_code is None
    assert result.status == "unknown"


def test_structured_salary_takes_precedence_over_label() -> None:
    result = normalize_salary(
        minimum_raw=Decimal("90000"),
        maximum_raw=Decimal("110000"),
        currency_raw="aud",
        period_raw="year",
        label_raw="$1 per hour",
    )

    assert result.minimum == Decimal("90000")
    assert result.maximum == Decimal("110000")
    assert result.currency == "AUD"
    assert result.period == "year"
    assert result.method == "structured"


def test_salary_label_fallback_preserves_period_and_boundaries() -> None:
    result = normalize_salary(
        minimum_raw=None,
        maximum_raw=None,
        currency_raw=None,
        period_raw=None,
        label_raw="$45 - $55 per hour",
    )

    assert result.minimum == Decimal("45")
    assert result.maximum == Decimal("55")
    assert result.currency == "AUD"
    assert result.period == "hour"
    assert result.method == "label_fallback"


@pytest.mark.parametrize(
    ("source_value", "expected_code"),
    [
        ("Full time", "full_time"),
        ("Part-time", "part_time"),
        ("Fixed-term contract", "temporary"),
    ],
)
def test_employment_type_normalization(source_value: str, expected_code: str) -> None:
    result = normalize_employment_types(source_value, ())

    assert expected_code in result.codes
    assert result.status == "known"


def test_work_mode_uses_structured_value_before_remote_flag() -> None:
    result = normalize_work_mode("Hybrid", False)

    assert result.code == "hybrid"
    assert result.method == "structured"
    assert result.status == "known"


def test_false_remote_flag_does_not_imply_onsite() -> None:
    result = normalize_work_mode(None, False)

    assert result.code == "unknown"
    assert result.method == "none"


def test_conflicting_work_mode_evidence_is_flagged() -> None:
    result = normalize_work_mode("On-site", True)

    assert result.code == "onsite"
    assert result.status == "conflict"
    assert result.quality_flags == ("conflicting_work_mode_evidence",)
