"""Test one paid scope boundary with a fake Apify client and no network use."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from skill_compass.collection.full_backfill import ApifyFullBackfillClient
from skill_compass.config.settings import load_apify_settings


class FakeActor:
    """Capture resolution and exactly one synchronous Actor call."""

    def __init__(self) -> None:
        self.get_count = 0
        self.call_arguments: dict[str, Any] | None = None

    def get(self) -> object:
        self.get_count += 1
        return object()

    def call(self, **arguments: Any) -> SimpleNamespace:
        self.call_arguments = arguments
        now = datetime(2026, 8, 13, 4, 5, 6, tzinfo=UTC)
        return SimpleNamespace(
            id="run-1",
            default_dataset_id="dataset-1",
            status="SUCCEEDED",
            started_at=now,
            finished_at=now,
        )


class FakeDataset:
    """Expose metadata and multiple logical raw pages through iteration."""

    def __init__(self) -> None:
        self.iterated = False

    def get(self) -> object:
        return object()

    def iterate_items(self):  # type: ignore[no-untyped-def]
        self.iterated = True
        yield {"id": "job-1"}
        yield {"id": "job-2"}


class FakeClient:
    """Provide only the Actor and dataset interfaces used by the adapter."""

    def __init__(self, token: str) -> None:
        self.token = token
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


def test_full_scope_call_waits_and_uses_unlimited_actor_input_only() -> None:
    clients: list[FakeClient] = []

    def factory(token: str) -> FakeClient:
        client = FakeClient(token)
        clients.append(client)
        return client

    adapter = ApifyFullBackfillClient(
        settings=load_apify_settings(environ={"APIFY_TOKEN": "fictional-token"}),
        actor_id="scrapersdelight/seek-jobs-scraper",
        client_factory=factory,
    )
    adapter.resolve_actor()
    dataset = adapter.execute_scope(
        {
            "keywords": "Data Analyst",
            "location": "Northern Territory NT",
            "maxItems": 0,
        }
    )
    items = tuple(dataset.items)

    client = clients[0]
    assert client.actor_id == "scrapersdelight/seek-jobs-scraper"
    assert client.actor_client.get_count == 1
    assert client.actor_client.call_arguments == {
        "run_input": {
            "keywords": "Data Analyst",
            "location": "Northern Territory NT",
            "maxItems": 0,
        },
        "logger": None,
    }
    assert "max_items" not in client.actor_client.call_arguments
    assert client.dataset_id == "dataset-1"
    assert items == ({"id": "job-1"}, {"id": "job-2"})
    assert client.dataset_client.iterated is True
