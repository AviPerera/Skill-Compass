"""Normalize structured canonical work arrangements before remote flags.

This cleaning-layer module permits explicit unknown and conflict states and
must not infer work mode from descriptions or treat false as proof of onsite.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkModeResult:
    """Hold a stable work-mode code plus method, status, and quality flags."""

    code: str
    method: str
    status: str
    quality_flags: tuple[str, ...] = ()


def structured_work_mode(value: str) -> str | None:
    """Recognize supported structured work-arrangement labels."""
    casefolded = value.casefold()
    if "hybrid" in casefolded:
        return "hybrid"
    if "remote" in casefolded or "work from home" in casefolded:
        return "remote"
    if any(
        marker in casefolded
        for marker in ("on-site", "onsite", "in office", "office based")
    ):
        return "onsite"
    return None


def normalize_work_mode(
    work_arrangement_raw: str | None, is_remote_raw: bool | None
) -> WorkModeResult:
    """Prefer a structured label and use only a positive remote flag as fallback."""
    if work_arrangement_raw and work_arrangement_raw.strip():
        code = structured_work_mode(work_arrangement_raw)
        if code is None:
            return WorkModeResult("unknown", "structured", "unknown")
        if code == "onsite" and is_remote_raw is True:
            return WorkModeResult(
                "onsite", "structured", "conflict", ("conflicting_work_mode_evidence",)
            )
        return WorkModeResult(code, "structured", "known")

    if is_remote_raw is True:
        return WorkModeResult("remote", "is_remote_flag", "known")
    return WorkModeResult("unknown", "none", "unknown")
