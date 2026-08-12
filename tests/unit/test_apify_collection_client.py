"""Test the Apify boundary with deterministic fakes and no paid requests."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from skill_compass.collection.apify_client import collect_connection_test
from skill_compass.collection.models import CapStatus
from skill_compass.collection.seek_adapter import load_seek_collection_config
from skill_compass.config.settings import (
    CollectionConfigurationError,
    load_apify_settings,
)
from skill_compass.services.apify_connection_test import run_apify_connection_test

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "sources/apify_seek_current/collection.yaml"


class FakeActor:
    """Capture Actor resolution and call arguments."""

    def __init__(self) -> None:
        self.call_arguments: dict[str, Any] | None = None

    def get(self) -> object:
        return object()

    def call(self, **arguments: Any) -> SimpleNamespace:
        self.call_arguments = arguments
        return SimpleNamespace(
            id="run-safe-1",
            default_dataset_id="dataset-safe-1",
            status="SUCCEEDED",
            started_at=datetime(2026, 8, 13, 1, 0, tzinfo=UTC),
            finished_at=datetime(2026, 8, 13, 1, 1, tzinfo=UTC),
        )


class FakeDataset:
    """Return five fictional raw JSON records."""

    def __init__(self) -> None:
        self.limit: int | None = None

    def list_items(self, *, limit: int) -> SimpleNamespace:
        self.limit = limit
        return SimpleNamespace(
            items=[{"id": f"fictional-{index}"} for index in range(5)]
        )


class FakeApifyClient:
    """Provide the minimal official-client interface used by the adapter."""

    def __init__(self, token: str) -> None:
        self.received_token = token
        self.actor_client = FakeActor()
        self.dataset_client = FakeDataset()
        self.actor_id: str | None = None
        self.dataset_id: str | None = None

    def actor(self, actor_id: str) -> FakeActor:
        self.actor_id = actor_id
        return self.actor_client

    def dataset(self, dataset_id: str) -> FakeDataset:
        self.dataset_id = dataset_id
        return self.dataset_client


def test_connection_test_enforces_both_five_item_limits() -> None:
    config = load_seek_collection_config(CONFIG_PATH)
    settings = load_apify_settings(environ={"APIFY_TOKEN": "private-token"})
    clients: list[FakeApifyClient] = []

    def factory(token: str) -> FakeApifyClient:
        client = FakeApifyClient(token)
        clients.append(client)
        return client

    response = collect_connection_test(
        settings=settings,
        config=config,
        client_factory=factory,
    )

    client = clients[0]
    assert client.actor_id == "scrapersdelight/seek-jobs-scraper"
    assert client.actor_client.call_arguments is not None
    assert client.actor_client.call_arguments["run_input"]["maxItems"] == 5
    assert client.actor_client.call_arguments["max_items"] == 5
    assert client.actor_client.call_arguments["logger"] is None
    assert client.dataset_client.limit == 5
    assert response.result.returned_item_count == 5
    assert response.result.unique_job_id_count == 5
    assert response.result.duplicate_job_id_count == 0
    assert response.result.cap_status is CapStatus.BELOW_THRESHOLD


def test_missing_token_fails_before_client_creation() -> None:
    client_created = False

    def factory(_token: str) -> FakeApifyClient:
        nonlocal client_created
        client_created = True
        return FakeApifyClient(_token)

    with pytest.raises(CollectionConfigurationError, match="APIFY_TOKEN is required"):
        run_apify_connection_test(
            config_path=CONFIG_PATH,
            environ={},
            client_factory=factory,
        )

    assert client_created is False


def test_secret_and_raw_items_are_not_printed_or_logged(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    token = "private-token-must-not-leak"

    run_apify_connection_test(
        config_path=CONFIG_PATH,
        environ={"APIFY_TOKEN": token},
        client_factory=FakeApifyClient,
    )

    captured = capsys.readouterr()
    assert token not in captured.out
    assert token not in captured.err
    assert token not in caplog.text
    assert "fictional-0" not in captured.out
