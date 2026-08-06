"""Parse canonical absolute and reference-based relative source dates.

This cleaning-layer module uses explicit source timestamps and must never use
the current computer time as an implicit relative-date reference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

# =============================================================================
# Typed parsing results
# =============================================================================


@dataclass(frozen=True, slots=True)
class DateParseResult:
    """Describe one parsed listing date and its deterministic method/status."""

    value: date | None
    method: str
    status: str


@dataclass(frozen=True, slots=True)
class TimestampParseResult:
    """Describe one parsed timestamp and its deterministic status."""

    value: datetime | None
    status: str


# =============================================================================
# Absolute and relative parsing
# =============================================================================


ABSOLUTE_DATE_FORMATS = (
    ("%d/%m/%Y", "australian_numeric"),
    ("%d %B %Y", "australian_long"),
    ("%d %b %Y", "australian_short"),
)
RELATIVE_DATE_PATTERN = re.compile(
    r"^(?P<amount>\d+)\s*(?P<unit>days?|d|hours?|h|weeks?|w)\s+ago$",
    re.IGNORECASE,
)


def parse_timestamp(value: str | None) -> TimestampParseResult:
    """Parse an ISO date or timestamp without fabricating a timezone."""
    if not value or not value.strip():
        return TimestampParseResult(None, "missing")

    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(normalized)
        except ValueError:
            return TimestampParseResult(None, "unparseable")
        parsed = datetime.combine(parsed_date, datetime.min.time())
    return TimestampParseResult(parsed, "parsed")


def parse_listing_date(
    value: str | None, reference_timestamp_raw: str | None
) -> DateParseResult:
    """Parse an absolute listing date or a relative value with an explicit reference."""
    if not value or not value.strip():
        return DateParseResult(None, "none", "missing")

    normalized = value.strip()
    iso_timestamp = parse_timestamp(normalized)
    if iso_timestamp.value is not None:
        return DateParseResult(iso_timestamp.value.date(), "iso", "parsed")

    for date_format, method in ABSOLUTE_DATE_FORMATS:
        try:
            parsed = datetime.strptime(normalized, date_format).date()
        except ValueError:
            continue
        return DateParseResult(parsed, method, "parsed")

    relative_match = RELATIVE_DATE_PATTERN.fullmatch(normalized)
    if relative_match is None:
        return DateParseResult(None, "none", "unparseable")

    reference = parse_timestamp(reference_timestamp_raw)
    if reference.value is None:
        return DateParseResult(None, "relative_without_reference", "unparseable")

    amount = int(relative_match.group("amount"))
    unit = relative_match.group("unit").casefold()
    if unit.startswith("w"):
        delta = timedelta(weeks=amount)
    elif unit.startswith("h"):
        delta = timedelta(hours=amount)
    else:
        delta = timedelta(days=amount)
    return DateParseResult(
        (reference.value - delta).date(), "relative_to_scraped_at", "parsed"
    )
