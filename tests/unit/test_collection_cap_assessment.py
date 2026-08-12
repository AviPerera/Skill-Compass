"""Test conservative collection-scope result-cap assessment."""

from skill_compass.collection.cap_assessment import assess_result_cap
from skill_compass.collection.models import CapStatus, CompletenessEvidence


def test_below_warning_threshold_is_below_threshold() -> None:
    assessment = assess_result_cap(returned_item_count=499, warning_threshold=500)

    assert assessment.status is CapStatus.BELOW_THRESHOLD


def test_exact_warning_threshold_is_only_cap_risk() -> None:
    assessment = assess_result_cap(returned_item_count=500, warning_threshold=500)

    assert assessment.status is CapStatus.CAP_RISK
    assert "no definitive truncation evidence" in assessment.reason


def test_above_warning_threshold_is_only_cap_risk() -> None:
    assessment = assess_result_cap(returned_item_count=501, warning_threshold=500)

    assert assessment.status is CapStatus.CAP_RISK


def test_explicit_available_total_confirms_truncation() -> None:
    evidence = CompletenessEvidence(
        total_available_count=700,
        evidence_source="verified Actor result metadata",
    )

    assessment = assess_result_cap(
        returned_item_count=500,
        warning_threshold=500,
        evidence=evidence,
    )

    assert assessment.status is CapStatus.CONFIRMED_TRUNCATED
    assert "700 available results" in assessment.reason


def test_explicit_flag_confirms_truncation() -> None:
    evidence = CompletenessEvidence(
        explicitly_truncated=True,
        evidence_source="verified Actor truncation flag",
    )

    assessment = assess_result_cap(
        returned_item_count=10,
        warning_threshold=500,
        evidence=evidence,
    )

    assert assessment.status is CapStatus.CONFIRMED_TRUNCATED


def test_missing_returned_count_is_unknown() -> None:
    assessment = assess_result_cap(returned_item_count=None, warning_threshold=500)

    assert assessment.status is CapStatus.UNKNOWN
