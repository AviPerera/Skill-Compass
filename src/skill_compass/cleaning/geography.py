"""Normalize canonical Australian location evidence without forced guesses.

This cleaning-layer module handles general state/city labels and the current
South Australian sample but must not depend on source-specific column names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from skill_compass.cleaning.text import normalize_inline_text

# =============================================================================
# Australian geography reference values
# =============================================================================


STATE_NAMES = {
    "ACT": "Australian Capital Territory",
    "NSW": "New South Wales",
    "NT": "Northern Territory",
    "QLD": "Queensland",
    "SA": "South Australia",
    "TAS": "Tasmania",
    "VIC": "Victoria",
    "WA": "Western Australia",
}
MAJOR_CITIES = {
    "adelaide": ("Adelaide", "SA"),
    "brisbane": ("Brisbane", "QLD"),
    "canberra": ("Canberra", "ACT"),
    "darwin": ("Darwin", "NT"),
    "hobart": ("Hobart", "TAS"),
    "melbourne": ("Melbourne", "VIC"),
    "perth": ("Perth", "WA"),
    "sydney": ("Sydney", "NSW"),
}


@dataclass(frozen=True, slots=True)
class GeographyResult:
    """Hold normalized Australian geography and explicit parse evidence."""

    country_code: str | None
    state_code: str | None
    state_name: str | None
    city_name: str | None
    suburb_name: str | None
    method: str
    status: str


# =============================================================================
# Canonical location parsing
# =============================================================================


def find_state(combined_text: str) -> tuple[str | None, str | None]:
    """Find a state code or full state name using boundary-aware matching."""
    for state_code, state_name in STATE_NAMES.items():
        code_pattern = rf"(?<![A-Za-z]){re.escape(state_code)}(?![A-Za-z])"
        if re.search(code_pattern, combined_text, flags=re.IGNORECASE):
            return state_code, state_name
        if state_name.casefold() in combined_text.casefold():
            return state_code, state_name
    return None, None


def find_city(combined_text: str) -> tuple[str | None, str | None]:
    """Find a major city and its state using canonical location evidence."""
    casefolded = combined_text.casefold()
    for city_key, city_data in MAJOR_CITIES.items():
        if re.search(rf"\b{re.escape(city_key)}\b", casefolded):
            return city_data
    return None, None


def find_suburb(location: str | None, city_name: str | None) -> str | None:
    """Extract a conservative leading suburb label when it is not the city."""
    normalized = normalize_inline_text(location)
    if not normalized:
        return None

    without_postcode = re.sub(r"\b\d{4}\b", "", normalized).strip(" ,-")
    leading = re.split(
        r",|\s+(?:ACT|NSW|NT|QLD|SA|TAS|VIC|WA)\b",
        without_postcode,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    if not leading or (city_name and leading.casefold() == city_name.casefold()):
        return None
    if leading.casefold() in {name.casefold() for name in STATE_NAMES.values()}:
        return None
    return leading


def normalize_geography(
    *,
    location_raw: str | None,
    location_long_raw: str | None,
    country_raw: str | None,
    country_code_raw: str | None,
    area_hierarchy_raw: tuple[str, ...],
) -> GeographyResult:
    """Normalize available canonical location evidence with explicit unknowns."""
    evidence = tuple(
        value
        for value in (location_raw, location_long_raw, *area_hierarchy_raw)
        if value and value.strip()
    )
    combined_text = " | ".join(evidence)

    raw_country_code = normalize_inline_text(country_code_raw)
    raw_country = normalize_inline_text(country_raw)
    country_code = None
    if raw_country_code and raw_country_code.upper() in {"AU", "AUS"}:
        country_code = "AU"
    elif raw_country and raw_country.casefold() == "australia":
        country_code = "AU"

    state_code, state_name = find_state(combined_text)
    city_name, city_state_code = find_city(combined_text)
    if state_code is None and city_state_code is not None:
        state_code = city_state_code
        state_name = STATE_NAMES[city_state_code]

    suburb_name = find_suburb(location_raw or location_long_raw, city_name)
    if not evidence:
        return GeographyResult(country_code, None, None, None, None, "none", "missing")
    if country_code == "AU" and (state_code or city_name):
        return GeographyResult(
            country_code,
            state_code,
            state_name,
            city_name,
            suburb_name,
            "australian_text",
            "parsed",
        )
    return GeographyResult(
        country_code,
        state_code,
        state_name,
        city_name,
        suburb_name,
        "australian_text",
        "unknown",
    )
