"""Persist an existing Apify dataset as raw JSONL with a safe manifest.

This application service coordinates storage retrieval and private raw output.
It must not invoke Actors, map fields, clean data, or run analytical processing.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from skill_compass.collection.apify_fetch import (
    iterate_existing_dataset,
    resolve_existing_dataset,
)
from skill_compass.collection.cap_assessment import assess_result_cap
from skill_compass.collection.models import FetchManifest
from skill_compass.collection.seek_adapter import (
    find_source_job_id,
    load_seek_collection_config,
)
from skill_compass.config.settings import load_apify_settings

# =============================================================================
# Fetch result and private output creation
# =============================================================================


DEFAULT_FETCH_OUTPUT_ROOT = Path("data/private/collections/fetched")


@dataclass(frozen=True, slots=True)
class ExistingDatasetFetchResult:
    """Return the typed manifest and both private output paths."""

    manifest: FetchManifest
    output_dir: Path
    items_path: Path
    manifest_path: Path


def _create_output_dir(
    *, output_root: Path, fetched_at: datetime, resource_id: str
) -> Path:
    """Create a unique UTC/resource folder without overwriting prior fetches."""
    timestamp = fetched_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"{timestamp}_{resource_id}"
    candidate = output_root / base_name
    suffix = 1
    while candidate.exists():
        candidate = output_root / f"{base_name}_{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def fetch_existing_apify_dataset(
    *,
    config_path: Path,
    dataset_id: str | None = None,
    run_id: str | None = None,
    output_root: Path = DEFAULT_FETCH_OUTPUT_ROOT,
    dotenv_path: Path = Path(".env"),
    environ: Mapping[str, str] | None = None,
    client_factory: Callable[[str], Any] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ExistingDatasetFetchResult:
    """Stream an existing dataset to JSONL and write its reconciled manifest."""
    settings = load_apify_settings(dotenv_path=dotenv_path, environ=environ)
    config = load_seek_collection_config(config_path)
    resolve_arguments: dict[str, Any] = {
        "settings": settings,
        "dataset_id": dataset_id,
        "run_id": run_id,
    }
    if client_factory is not None:
        resolve_arguments["client_factory"] = client_factory
    resolved = resolve_existing_dataset(**resolve_arguments)

    fetched_at = clock()
    if fetched_at.tzinfo is None:
        raise ValueError("fetch clock must return a timezone-aware datetime")
    resource_id = resolved.run_id or resolved.dataset_id
    output_dir = _create_output_dir(
        output_root=output_root,
        fetched_at=fetched_at,
        resource_id=resource_id,
    )
    items_path = output_dir / "items.jsonl"
    manifest_path = output_dir / "fetch_manifest.json"
    partial_items_path = output_dir / "items.jsonl.partial"
    partial_manifest_path = output_dir / "fetch_manifest.json.partial"

    returned_count = 0
    identities_are_complete = True
    seen_source_job_ids: set[str] = set()
    duplicate_count = 0

    with partial_items_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for item in iterate_existing_dataset(resolved):
            output_file.write(
                json.dumps(item, ensure_ascii=False, separators=(",", ":"))
            )
            output_file.write("\n")
            returned_count += 1

            source_job_id = find_source_job_id(item, config.source_job_id_paths)
            if source_job_id is None:
                identities_are_complete = False
            elif source_job_id in seen_source_job_ids:
                duplicate_count += 1
            else:
                seen_source_job_ids.add(source_job_id)
    partial_items_path.replace(items_path)

    unique_count = len(seen_source_job_ids) if identities_are_complete else None
    reconciled_duplicate_count = duplicate_count if identities_are_complete else None
    cap = assess_result_cap(
        returned_item_count=returned_count,
        warning_threshold=config.cap_warning_threshold,
    )
    manifest = FetchManifest(
        fetched_at=fetched_at,
        run_id=resolved.run_id,
        dataset_id=resolved.dataset_id,
        returned_item_count=returned_count,
        unique_source_job_id_count=unique_count,
        duplicate_source_job_id_count=reconciled_duplicate_count,
        cap_warning_threshold=config.cap_warning_threshold,
        cap_status=cap.status,
        cap_reason=cap.reason,
        source_actor_id=resolved.source_actor_id,
        raw_output_path=items_path.resolve(),
        status="SUCCEEDED",
        actor_invocation=False,
    )
    partial_manifest_path.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    partial_manifest_path.replace(manifest_path)
    return ExistingDatasetFetchResult(
        manifest=manifest,
        output_dir=output_dir,
        items_path=items_path,
        manifest_path=manifest_path,
    )
