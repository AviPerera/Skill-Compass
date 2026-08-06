"""Normalize canonical employment labels into stable deterministic codes.

This cleaning-layer module handles already mapped values and must not infer
employment from descriptions or implement source-specific precedence.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmploymentResult:
    """Hold stable employment codes and an explicit normalization status."""

    codes: tuple[str, ...]
    status: str


EMPLOYMENT_MARKERS = (
    ("full_time", ("full time", "full-time", "permanent full")),
    ("part_time", ("part time", "part-time")),
    ("internship", ("intern", "internship", "graduate program")),
    ("casual", ("casual",)),
    ("temporary", ("temporary", "temp ", "fixed term", "fixed-term")),
    ("contract", ("contract", "contractor")),
)


def normalize_employment_types(
    work_type_raw: str | None, work_types_raw: tuple[str, ...]
) -> EmploymentResult:
    """Normalize one or more canonical source employment labels."""
    values = work_types_raw or ((work_type_raw,) if work_type_raw else ())
    codes: list[str] = []
    unknown_value_found = False

    for value in values:
        casefolded = value.casefold().strip()
        matched_code = next(
            (
                code
                for code, markers in EMPLOYMENT_MARKERS
                if any(marker in casefolded for marker in markers)
            ),
            None,
        )
        if matched_code is None:
            unknown_value_found = True
        elif matched_code not in codes:
            codes.append(matched_code)

    if not values or not codes:
        return EmploymentResult(("unknown",), "unknown")
    return EmploymentResult(tuple(codes), "partial" if unknown_value_found else "known")
