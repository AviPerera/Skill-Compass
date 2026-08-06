"""Normalize structured canonical salary values with a label fallback.

This cleaning-layer module preserves source periods and boundaries and must not
silently annualize, infer missing bounds, or inspect source-specific fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# =============================================================================
# Salary parsing contract and reference rules
# =============================================================================


@dataclass(frozen=True, slots=True)
class SalaryResult:
    """Hold normalized salary values and explicit parse evidence."""

    minimum: Decimal | None
    maximum: Decimal | None
    currency: str | None
    period: str | None
    method: str
    status: str


NUMBER_PATTERN = re.compile(r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*([kK])?")
PERIOD_PATTERNS = (
    (re.compile(r"\b(?:per\s+)?hours?\b|/\s*h(?:r)?\b", re.IGNORECASE), "hour"),
    (re.compile(r"\b(?:per\s+)?days?\b|/\s*day\b", re.IGNORECASE), "day"),
    (re.compile(r"\b(?:per\s+)?weeks?\b", re.IGNORECASE), "week"),
    (re.compile(r"\b(?:per\s+)?months?\b", re.IGNORECASE), "month"),
    (
        re.compile(
            r"\b(?:per\s+)?years?\b|\bannual(?:ly)?\b|\bp\.?a\.?\b", re.IGNORECASE
        ),
        "year",
    ),
)
PERIOD_ALIASES = {
    "annual": "year",
    "annually": "year",
    "day": "day",
    "daily": "day",
    "hour": "hour",
    "hourly": "hour",
    "month": "month",
    "monthly": "month",
    "week": "week",
    "weekly": "week",
    "year": "year",
    "yearly": "year",
}


def normalize_period(value: str | None, label: str | None) -> str | None:
    """Normalize an explicit period first, then inspect a salary label."""
    if value and value.strip():
        normalized = value.strip().casefold().replace("per ", "")
        if normalized in PERIOD_ALIASES:
            return PERIOD_ALIASES[normalized]
    if label:
        for pattern, period in PERIOD_PATTERNS:
            if pattern.search(label):
                return period
    return None


def salary_number(number: str, suffix: str) -> Decimal | None:
    """Convert one salary-label number, including an explicit k suffix."""
    try:
        value = Decimal(number.replace(",", ""))
    except InvalidOperation:
        return None
    return value * 1000 if suffix.casefold() == "k" else value


def parse_salary_label(label: str) -> tuple[Decimal | None, Decimal | None]:
    """Parse explicit label boundaries without inventing a missing bound."""
    values = [
        parsed
        for match in NUMBER_PATTERN.finditer(label)
        if (parsed := salary_number(match.group(1), match.group(2) or "")) is not None
    ]
    if len(values) >= 2:
        return values[0], values[1]
    if not values:
        return None, None

    lowered = label.casefold()
    if "up to" in lowered or "maximum" in lowered or "max " in lowered:
        return None, values[0]
    if "from" in lowered or "minimum" in lowered or "min " in lowered:
        return values[0], None
    return values[0], values[0]


def normalize_salary(
    *,
    minimum_raw: Decimal | None,
    maximum_raw: Decimal | None,
    currency_raw: str | None,
    period_raw: str | None,
    label_raw: str | None,
) -> SalaryResult:
    """Prefer structured salary values and fall back to an explicit label parse."""
    currency = currency_raw.strip().upper() if currency_raw else None
    period = normalize_period(period_raw, label_raw)

    if minimum_raw is not None or maximum_raw is not None:
        if (
            minimum_raw is not None
            and maximum_raw is not None
            and minimum_raw > maximum_raw
        ):
            return SalaryResult(
                minimum_raw,
                maximum_raw,
                currency,
                period,
                "structured",
                "invalid_range",
            )
        return SalaryResult(
            minimum_raw,
            maximum_raw,
            currency,
            period,
            "structured",
            "parsed",
        )

    if not label_raw or not label_raw.strip():
        return SalaryResult(None, None, currency, period, "none", "unknown")

    minimum, maximum = parse_salary_label(label_raw)
    if minimum is None and maximum is None:
        return SalaryResult(None, None, currency, period, "none", "unknown")
    if currency is None and "$" in label_raw:
        currency = "AUD"
    if minimum is not None and maximum is not None and minimum > maximum:
        return SalaryResult(
            minimum,
            maximum,
            currency,
            period,
            "label_fallback",
            "invalid_range",
        )
    return SalaryResult(
        minimum,
        maximum,
        currency,
        period,
        "label_fallback",
        "parsed",
    )
