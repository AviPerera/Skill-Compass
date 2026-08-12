"""Assess collection-scope result-cap risk from explicit evidence.

This generic collection logic must not assume SEEK or Apify field names and
must never equate a threshold-sized result with proven truncation.
"""

from __future__ import annotations

from skill_compass.collection.models import (
    CapAssessment,
    CapStatus,
    CompletenessEvidence,
)

# =============================================================================
# Conservative cap assessment
# =============================================================================


def assess_result_cap(
    *,
    returned_item_count: int | None,
    warning_threshold: int = 500,
    evidence: CompletenessEvidence | None = None,
) -> CapAssessment:
    """Assess scope completeness without overstating threshold-only evidence."""
    if warning_threshold <= 0:
        raise ValueError("warning_threshold must be greater than zero")
    if returned_item_count is None or returned_item_count < 0:
        return CapAssessment(
            status=CapStatus.UNKNOWN,
            reason="Returned item count is unavailable or unreliable.",
        )

    if evidence is not None and evidence.explicitly_truncated is True:
        source = evidence.evidence_source or "verified source metadata"
        return CapAssessment(
            status=CapStatus.CONFIRMED_TRUNCATED,
            reason=f"{source} explicitly reports truncation.",
        )

    if (
        evidence is not None
        and evidence.total_available_count is not None
        and evidence.total_available_count > returned_item_count
    ):
        source = evidence.evidence_source or "verified source metadata"
        return CapAssessment(
            status=CapStatus.CONFIRMED_TRUNCATED,
            reason=(
                f"{source} reports {evidence.total_available_count} available results "
                f"but only {returned_item_count} were retrieved."
            ),
        )

    if returned_item_count >= warning_threshold:
        return CapAssessment(
            status=CapStatus.CAP_RISK,
            reason=(
                f"Returned item count {returned_item_count} is at or above the "
                f"warning threshold {warning_threshold}; no definitive truncation "
                "evidence is available."
            ),
        )

    return CapAssessment(
        status=CapStatus.BELOW_THRESHOLD,
        reason=(
            f"Returned item count {returned_item_count} is below the warning "
            f"threshold {warning_threshold}, with no explicit truncation evidence."
        ),
    )
