"""Execute one configured full-backfill scope through the approved SEEK Actor.

This collection adapter owns paid Actor invocation and raw dataset access. It
must not orchestrate multiple scopes, persist files, consolidate, or process jobs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from apify_client import ApifyClient
from apify_client.errors import ApifyClientError

from skill_compass.collection.apify_client import ApifyCollectionError
from skill_compass.config.settings import ApifySettings

# =============================================================================
# One-scope Actor result
# =============================================================================


@dataclass(frozen=True, slots=True)
class ScopeDataset:
    """Expose completed Actor metadata and an all-pages raw item iterator."""

    run_id: str
    dataset_id: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    items: Iterator[dict[str, Any]]


def _status_value(status: Any) -> str:
    """Normalize Apify status enums while accepting deterministic test doubles."""
    return str(getattr(status, "value", status)).upper()


def _iterate_raw_items(dataset_client: Any) -> Iterator[dict[str, Any]]:
    """Yield all raw dataset pages and convert client failures to safe errors."""
    try:
        for item in dataset_client.iterate_items():
            if not isinstance(item, dict):
                raise ApifyCollectionError(
                    "Apify dataset returned an item that is not a JSON object"
                )
            yield item
    except ApifyCollectionError:
        raise
    except ApifyClientError as error:
        raise ApifyCollectionError(
            "Apify dataset iteration failed before all items were retrieved"
        ) from error


# =============================================================================
# Reusable sequential client
# =============================================================================


class ApifyFullBackfillClient:
    """Reuse one authenticated client while running scopes sequentially."""

    def __init__(
        self,
        *,
        settings: ApifySettings,
        actor_id: str,
        client_factory: Callable[[str], Any] = ApifyClient,
    ) -> None:
        self._client = client_factory(settings.token.get_secret_value())
        self._actor = self._client.actor(actor_id)

    def resolve_actor(self) -> None:
        """Verify the configured Actor exists before the first paid scope call."""
        try:
            if self._actor.get() is None:
                raise ApifyCollectionError(
                    "configured Apify Actor could not be resolved"
                )
        except ApifyCollectionError:
            raise
        except ApifyClientError as error:
            raise ApifyCollectionError(
                "Apify Actor lookup failed; check token and Actor access"
            ) from error

    def execute_scope(self, actor_input: Mapping[str, Any]) -> ScopeDataset:
        """Start exactly one Actor run, wait, and expose its complete raw dataset."""
        try:
            run = self._actor.call(run_input=dict(actor_input), logger=None)
            if run is None:
                raise ApifyCollectionError("Apify Actor did not return a completed run")
            status = _status_value(run.status)
            if status != "SUCCEEDED":
                raise ApifyCollectionError(
                    f"Apify Actor run ended with status {status}"
                )
            dataset_client = self._client.dataset(run.default_dataset_id)
            if dataset_client.get() is None:
                raise ApifyCollectionError("completed Actor dataset was not found")
        except ApifyCollectionError:
            raise
        except ApifyClientError as error:
            raise ApifyCollectionError(
                "Apify scope request failed; check Actor access and input contract"
            ) from error

        return ScopeDataset(
            run_id=run.id,
            dataset_id=run.default_dataset_id,
            status=status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            items=_iterate_raw_items(dataset_client),
        )

    def retrieve_existing_scope_dataset(
        self,
        *,
        run_id: str,
        dataset_id: str,
        started_at: datetime,
        finished_at: datetime | None,
    ) -> ScopeDataset:
        """Resume retrieval from a known successful run without another Actor call."""
        try:
            dataset_client = self._client.dataset(dataset_id)
            if dataset_client.get() is None:
                raise ApifyCollectionError("previous scope dataset was not found")
        except ApifyCollectionError:
            raise
        except ApifyClientError as error:
            raise ApifyCollectionError(
                "previous scope dataset could not be retrieved"
            ) from error
        return ScopeDataset(
            run_id=run_id,
            dataset_id=dataset_id,
            status="SUCCEEDED",
            started_at=started_at,
            finished_at=finished_at,
            items=_iterate_raw_items(dataset_client),
        )
