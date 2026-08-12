"""Invoke an approved Apify Actor and retrieve its bounded raw dataset.

This source collection adapter owns Apify API interactions. It must not print
tokens or raw records, convert data to analytical CSV, or run processing logic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from apify_client import ApifyClient
from apify_client.errors import ApifyClientError

from skill_compass.collection.cap_assessment import assess_result_cap
from skill_compass.collection.models import CollectionResult
from skill_compass.collection.seek_adapter import (
    SeekCollectionConfig,
    count_source_job_ids,
)
from skill_compass.config.settings import ApifySettings

# =============================================================================
# Safe adapter result and errors
# =============================================================================


class ApifyCollectionError(RuntimeError):
    """Report a safe external collection failure without response details."""


@dataclass(frozen=True, slots=True)
class ApifyCollectionResponse:
    """Keep raw JSON items beside their typed, privacy-safe run summary."""

    result: CollectionResult
    items: tuple[dict[str, Any], ...]


def _status_value(status: Any) -> str:
    """Normalize Apify status enums while accepting simple test doubles."""
    return str(getattr(status, "value", status)).upper()


# =============================================================================
# Explicit bounded connection test
# =============================================================================


def collect_connection_test(
    *,
    settings: ApifySettings,
    config: SeekCollectionConfig,
    client_factory: Callable[[str], Any] = ApifyClient,
) -> ApifyCollectionResponse:
    """Resolve and run the approved Actor with two independent five-item limits."""
    token = settings.token.get_secret_value()
    try:
        client = client_factory(token)
        actor = client.actor(config.actor_id)
        if actor.get() is None:
            raise ApifyCollectionError("configured Apify Actor could not be resolved")

        test_config = config.connection_test
        run_input = dict(test_config.actor_input)
        run_input["maxItems"] = test_config.max_items
        run = actor.call(
            run_input=run_input,
            max_items=test_config.max_items,
            logger=None,
        )
        if run is None:
            raise ApifyCollectionError("Apify Actor did not return a completed run")

        status = _status_value(run.status)
        if status != "SUCCEEDED":
            raise ApifyCollectionError(f"Apify Actor run ended with status {status}")

        dataset = client.dataset(run.default_dataset_id)
        page = dataset.list_items(limit=test_config.max_items)
    except ApifyCollectionError:
        raise
    except ApifyClientError as error:
        raise ApifyCollectionError(
            "Apify request failed; check the token, Actor access, and input contract"
        ) from error

    items = tuple(page.items)
    unique_count, duplicate_count = count_source_job_ids(
        items, config.source_job_id_paths
    )

    # Generic Apify run/dataset metadata has no verified pre-limit SEEK total or
    # truncation flag, so no completeness evidence is manufactured here.
    cap = assess_result_cap(
        returned_item_count=len(items),
        warning_threshold=config.cap_warning_threshold,
    )
    result = CollectionResult(
        scope_id=test_config.scope_id,
        run_id=run.id,
        dataset_id=run.default_dataset_id,
        returned_item_count=len(items),
        unique_job_id_count=unique_count,
        duplicate_job_id_count=duplicate_count,
        cap_warning_threshold=config.cap_warning_threshold,
        cap_status=cap.status,
        cap_reason=cap.reason,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=status,
    )
    return ApifyCollectionResponse(result=result, items=items)
