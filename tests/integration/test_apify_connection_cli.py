"""Test the explicit connection CLI without making an Apify request."""

from datetime import UTC, datetime

import pytest

from skill_compass.cli import main
from skill_compass.collection.apify_client import ApifyCollectionResponse
from skill_compass.collection.models import CapStatus, CollectionResult


def test_apify_connection_cli_prints_only_safe_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = CollectionResult(
        scope_id="safe-test-scope",
        run_id="run-1",
        dataset_id="dataset-1",
        returned_item_count=5,
        unique_job_id_count=5,
        duplicate_job_id_count=0,
        cap_warning_threshold=500,
        cap_status=CapStatus.BELOW_THRESHOLD,
        cap_reason="Below threshold.",
        started_at=datetime(2026, 8, 13, 1, 0, tzinfo=UTC),
        finished_at=datetime(2026, 8, 13, 1, 1, tzinfo=UTC),
        status="SUCCEEDED",
    )
    response = ApifyCollectionResponse(
        result=result,
        items=({"description": "private full description"},),
    )
    monkeypatch.setattr(
        "skill_compass.cli.run_apify_connection_test",
        lambda **_arguments: response,
    )

    exit_code = main(["test-apify-connection"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Actor connection: PASS" in output
    assert "Run status: SUCCEEDED" in output
    assert "Items retrieved: 5" in output
    assert "Cap assessment: BELOW_THRESHOLD" in output
    assert "No processing or analysis was executed." in output
    assert "private full description" not in output
