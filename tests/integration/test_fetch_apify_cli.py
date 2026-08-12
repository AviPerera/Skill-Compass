"""Test the explicit no-Actor fetch CLI with no external API requests."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from skill_compass.cli import main
from skill_compass.collection.models import CapStatus, FetchManifest
from skill_compass.services.fetch_apify import ExistingDatasetFetchResult


def test_fetch_apify_cli_states_actor_was_not_invoked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    items_path = tmp_path / "items.jsonl"
    manifest_path = tmp_path / "fetch_manifest.json"
    manifest = FetchManifest(
        fetched_at=datetime(2026, 8, 13, 3, 4, 5, tzinfo=UTC),
        run_id="existing-run-1",
        dataset_id="existing-dataset-1",
        returned_item_count=2,
        unique_source_job_id_count=2,
        duplicate_source_job_id_count=0,
        cap_warning_threshold=500,
        cap_status=CapStatus.BELOW_THRESHOLD,
        cap_reason="Below threshold.",
        source_actor_id="existing-actor-1",
        raw_output_path=items_path,
        status="SUCCEEDED",
        actor_invocation=False,
    )
    result = ExistingDatasetFetchResult(
        manifest=manifest,
        output_dir=tmp_path,
        items_path=items_path,
        manifest_path=manifest_path,
    )
    monkeypatch.setattr(
        "skill_compass.cli.fetch_existing_apify_dataset",
        lambda **_arguments: result,
    )

    exit_code = main(["fetch-apify", "--dataset-id", "existing-dataset-1"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Actor invocation: NO" in output
    assert "Existing dataset fetch only" in output
    assert "Dataset ID: existing-dataset-1" in output
    assert "Items retrieved: 2" in output
    assert "No processing or analysis was executed." in output
