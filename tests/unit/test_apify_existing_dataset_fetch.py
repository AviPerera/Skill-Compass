"""Test no-Actor Apify fetches, pagination, and private raw manifests."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from skill_compass.collection.apify_client import ApifyCollectionError
from skill_compass.collection.apify_fetch import resolve_existing_dataset
from skill_compass.collection.models import CapStatus
from skill_compass.config.settings import load_apify_settings
from skill_compass.services.fetch_apify import fetch_existing_apify_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "sources/apify_seek_current/collection.yaml"
FIXED_TIME = datetime(2026, 8, 13, 3, 4, 5, tzinfo=UTC)


class FakeDatasetClient:
    """Expose existing metadata and simulated pages through iteration only."""

    def __init__(
        self,
        *,
        pages: tuple[tuple[dict[str, Any], ...], ...] = (),
        exists: bool = True,
        run_id: str | None = "existing-run-1",
        actor_id: str | None = "existing-actor-1",
    ) -> None:
        self.pages = pages
        self.exists = exists
        self.run_id = run_id
        self.actor_id = actor_id
        self.iterate_items_called = False

    def get(self) -> SimpleNamespace | None:
        if not self.exists:
            return None
        return SimpleNamespace(act_run_id=self.run_id, act_id=self.actor_id)

    def iterate_items(self):  # type: ignore[no-untyped-def]
        self.iterate_items_called = True
        for page in self.pages:
            yield from page


class FakeRunClient:
    """Resolve one existing run without starting or calling it."""

    def __init__(self, run: SimpleNamespace | None) -> None:
        self.existing_run = run
        self.get_called = False

    def get(self) -> SimpleNamespace | None:
        self.get_called = True
        return self.existing_run


class FakeApifyClient:
    """Fail immediately if production code attempts Actor access."""

    def __init__(
        self,
        token: str,
        *,
        dataset_client: FakeDatasetClient,
        run: SimpleNamespace | None = None,
    ) -> None:
        self.token = token
        self.dataset_client = dataset_client
        self.run_client = FakeRunClient(run)
        self.requested_dataset_id: str | None = None
        self.requested_run_id: str | None = None

    def actor(self, _actor_id: str) -> None:
        raise AssertionError("fetch-apify must never access an Actor client")

    def dataset(self, dataset_id: str) -> FakeDatasetClient:
        self.requested_dataset_id = dataset_id
        return self.dataset_client

    def run(self, run_id: str) -> FakeRunClient:
        self.requested_run_id = run_id
        return self.run_client


def _factory_for(client: FakeApifyClient):  # type: ignore[no-untyped-def]
    return lambda _token: client


def test_dataset_id_fetch_streams_all_pages_and_writes_safe_manifest(
    tmp_path: Path,
) -> None:
    raw_items = (
        ({"id": "job-1", "nested": {"description": "raw private one"}},),
        (
            {"id": "job-1", "nested": {"description": "raw private duplicate"}},
            {"id": "job-2", "unicode": "café"},
        ),
    )
    dataset_client = FakeDatasetClient(pages=raw_items)
    client = FakeApifyClient("private-token", dataset_client=dataset_client)

    result = fetch_existing_apify_dataset(
        config_path=CONFIG_PATH,
        dataset_id="existing-dataset-1",
        output_root=tmp_path,
        environ={"APIFY_TOKEN": "private-token"},
        client_factory=_factory_for(client),
        clock=lambda: FIXED_TIME,
    )

    assert dataset_client.iterate_items_called is True
    assert client.requested_dataset_id == "existing-dataset-1"
    assert result.output_dir.name == "20260813T030405Z_existing-run-1"
    jsonl_items = [
        json.loads(line)
        for line in result.items_path.read_text(encoding="utf-8").splitlines()
    ]
    assert jsonl_items == [item for page in raw_items for item in page]

    manifest_document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest_document["returned_item_count"] == 3
    assert manifest_document["unique_source_job_id_count"] == 2
    assert manifest_document["duplicate_source_job_id_count"] == 1
    assert manifest_document["cap_status"] == "BELOW_THRESHOLD"
    assert manifest_document["actor_invocation"] is False
    assert manifest_document["source_actor_id"] == "existing-actor-1"
    assert manifest_document["raw_output_path"] == str(result.items_path.resolve())
    assert "raw private" not in result.manifest_path.read_text(encoding="utf-8")


def test_run_id_resolves_default_dataset_without_actor_invocation(
    tmp_path: Path,
) -> None:
    run = SimpleNamespace(
        default_dataset_id="resolved-dataset-1",
        act_id="run-actor-1",
    )
    dataset_client = FakeDatasetClient(pages=(({"id": "job-1"},),))
    client = FakeApifyClient(
        "private-token",
        dataset_client=dataset_client,
        run=run,
    )

    result = fetch_existing_apify_dataset(
        config_path=CONFIG_PATH,
        run_id="existing-run-2",
        output_root=tmp_path,
        environ={"APIFY_TOKEN": "private-token"},
        client_factory=_factory_for(client),
        clock=lambda: FIXED_TIME,
    )

    assert client.requested_run_id == "existing-run-2"
    assert client.requested_dataset_id == "resolved-dataset-1"
    assert client.run_client.get_called is True
    assert result.manifest.run_id == "existing-run-2"
    assert result.manifest.dataset_id == "resolved-dataset-1"
    assert result.manifest.source_actor_id == "run-actor-1"
    assert result.manifest.actor_invocation is False


def test_empty_dataset_writes_empty_jsonl_and_zero_counts(tmp_path: Path) -> None:
    dataset_client = FakeDatasetClient(pages=())
    client = FakeApifyClient("private-token", dataset_client=dataset_client)

    result = fetch_existing_apify_dataset(
        config_path=CONFIG_PATH,
        dataset_id="empty-dataset-1",
        output_root=tmp_path,
        environ={"APIFY_TOKEN": "private-token"},
        client_factory=_factory_for(client),
        clock=lambda: FIXED_TIME,
    )

    assert result.items_path.read_bytes() == b""
    assert result.manifest.returned_item_count == 0
    assert result.manifest.unique_source_job_id_count == 0
    assert result.manifest.duplicate_source_job_id_count == 0
    assert result.manifest.cap_status is CapStatus.BELOW_THRESHOLD


def test_threshold_sized_existing_dataset_reuses_cap_risk(tmp_path: Path) -> None:
    items = tuple({"id": f"job-{index}"} for index in range(500))
    dataset_client = FakeDatasetClient(pages=(items,))
    client = FakeApifyClient("private-token", dataset_client=dataset_client)

    result = fetch_existing_apify_dataset(
        config_path=CONFIG_PATH,
        dataset_id="threshold-dataset-1",
        output_root=tmp_path,
        environ={"APIFY_TOKEN": "private-token"},
        client_factory=_factory_for(client),
        clock=lambda: FIXED_TIME,
    )

    assert result.manifest.returned_item_count == 500
    assert result.manifest.cap_status is CapStatus.CAP_RISK
    assert "no definitive truncation evidence" in result.manifest.cap_reason


def test_invalid_and_nonexistent_dataset_ids_fail_safely() -> None:
    settings = load_apify_settings(environ={"APIFY_TOKEN": "private-token"})
    dataset_client = FakeDatasetClient(exists=False)
    client = FakeApifyClient("private-token", dataset_client=dataset_client)

    with pytest.raises(ApifyCollectionError, match="dataset_id must contain"):
        resolve_existing_dataset(
            settings=settings,
            dataset_id="../unsafe",
            client_factory=_factory_for(client),
        )

    with pytest.raises(ApifyCollectionError, match="dataset was not found"):
        resolve_existing_dataset(
            settings=settings,
            dataset_id="missing-dataset-1",
            client_factory=_factory_for(client),
        )


def test_nonexistent_run_id_fails_before_dataset_access() -> None:
    settings = load_apify_settings(environ={"APIFY_TOKEN": "private-token"})
    dataset_client = FakeDatasetClient()
    client = FakeApifyClient(
        "private-token",
        dataset_client=dataset_client,
        run=None,
    )

    with pytest.raises(ApifyCollectionError, match="run was not found"):
        resolve_existing_dataset(
            settings=settings,
            run_id="missing-run-1",
            client_factory=_factory_for(client),
        )

    assert client.requested_dataset_id is None
