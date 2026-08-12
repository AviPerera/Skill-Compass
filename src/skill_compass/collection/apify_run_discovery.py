"""Discover existing successful Apify Actor runs without invoking an Actor.

This source collection adapter may list completed run metadata for one approved
Actor. It must never start, call, restart, abort, or otherwise mutate a run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from apify_client.errors import ApifyClientError

from skill_compass.collection.apify_client import ApifyCollectionError

# =============================================================================
# Existing successful-run discovery
# =============================================================================


_RESOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class ExistingActorDataset:
    """Identify one successful existing Actor run and its default dataset."""

    run_id: str
    dataset_id: str
    started_at: datetime


def _resource_id(value: Any, label: str) -> str:
    """Validate one SDK resource identifier before local persistence."""
    normalized = str(value or "").strip()
    if not normalized or not _RESOURCE_ID_PATTERN.fullmatch(normalized):
        raise ApifyCollectionError(f"discovered {label} is missing or invalid")
    return normalized


def discover_successful_actor_datasets(
    *, client: Any, actor_id: str
) -> tuple[ExistingActorDataset, ...]:
    """Iterate every successful run and return deterministic dataset references."""
    if not actor_id.strip():
        raise ApifyCollectionError("supplemental discovery actor ID is required")
    discovered: list[ExistingActorDataset] = []
    try:
        run_iterator = (
            client.actor(actor_id)
            .runs()
            .iterate(
                status="SUCCEEDED",
                desc=False,
            )
        )
        for run in run_iterator:
            started_at = getattr(run, "started_at", None)
            if not isinstance(started_at, datetime) or started_at.tzinfo is None:
                raise ApifyCollectionError(
                    "discovered successful run has no timezone-aware start time"
                )
            discovered.append(
                ExistingActorDataset(
                    run_id=_resource_id(getattr(run, "id", None), "run ID"),
                    dataset_id=_resource_id(
                        getattr(run, "default_dataset_id", None),
                        "default dataset ID",
                    ),
                    started_at=started_at,
                )
            )
    except ApifyCollectionError:
        raise
    except ApifyClientError as error:
        raise ApifyCollectionError(
            "Apify successful-run discovery failed; no Actor was invoked"
        ) from error

    return tuple(sorted(discovered, key=lambda item: (item.started_at, item.run_id)))
