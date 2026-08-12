"""Resolve and iterate an existing Apify dataset without invoking an Actor.

This source collection adapter may read run and dataset metadata and raw items.
It must never start an Actor, transform records, or persist analytical output.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from apify_client import ApifyClient
from apify_client.errors import ApifyClientError

from skill_compass.collection.apify_client import ApifyCollectionError
from skill_compass.config.settings import ApifySettings

# =============================================================================
# Existing storage resolution
# =============================================================================


_STORAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class ResolvedApifyDataset:
    """Hold verified existing-storage metadata and its dataset client."""

    run_id: str | None
    dataset_id: str
    source_actor_id: str | None
    dataset_client: Any


def _validate_resource_id(value: str, label: str) -> str:
    """Reject blank or path-like identifiers before constructing an API client."""
    normalized = value.strip()
    if not normalized or not _STORAGE_ID_PATTERN.fullmatch(normalized):
        raise ApifyCollectionError(
            f"{label} must contain only letters, numbers, underscores, or hyphens"
        )
    return normalized


def resolve_existing_dataset(
    *,
    settings: ApifySettings,
    dataset_id: str | None = None,
    run_id: str | None = None,
    client_factory: Callable[[str], Any] = ApifyClient,
) -> ResolvedApifyDataset:
    """Resolve one existing dataset using only run and dataset GET requests."""
    if (dataset_id is None) == (run_id is None):
        raise ApifyCollectionError("provide exactly one of dataset_id or run_id")

    if run_id is not None:
        requested_run_id = _validate_resource_id(run_id, "run_id")
        requested_dataset_id = None
    else:
        requested_run_id = None
        requested_dataset_id = _validate_resource_id(dataset_id or "", "dataset_id")

    resolved_dataset_id: str
    resolved_run_id: str | None = requested_run_id
    source_actor_id: str | None = None
    token = settings.token.get_secret_value()

    try:
        client = client_factory(token)
        if requested_run_id is not None:
            run = client.run(requested_run_id).get()
            if run is None:
                raise ApifyCollectionError("Apify run was not found")
            resolved_dataset_id = _validate_resource_id(
                run.default_dataset_id, "default dataset ID"
            )
            source_actor_id = getattr(run, "act_id", None)
        else:
            assert requested_dataset_id is not None
            resolved_dataset_id = requested_dataset_id

        dataset_client = client.dataset(resolved_dataset_id)
        dataset = dataset_client.get()
        if dataset is None:
            raise ApifyCollectionError("Apify dataset was not found")

        if resolved_run_id is None:
            metadata_run_id = getattr(dataset, "act_run_id", None)
            if metadata_run_id is not None:
                resolved_run_id = _validate_resource_id(
                    metadata_run_id, "dataset run ID"
                )
        if source_actor_id is None:
            source_actor_id = getattr(dataset, "act_id", None)
    except ApifyCollectionError:
        raise
    except ApifyClientError as error:
        raise ApifyCollectionError(
            "Apify lookup failed; check the token and supplied identifier"
        ) from error

    return ResolvedApifyDataset(
        run_id=resolved_run_id,
        dataset_id=resolved_dataset_id,
        source_actor_id=source_actor_id,
        dataset_client=dataset_client,
    )


# =============================================================================
# Paginated raw item iteration
# =============================================================================


def iterate_existing_dataset(
    resolved: ResolvedApifyDataset,
) -> Iterator[dict[str, Any]]:
    """Yield every raw item through Apify's multi-page dataset iterator."""
    try:
        for item in resolved.dataset_client.iterate_items():
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
