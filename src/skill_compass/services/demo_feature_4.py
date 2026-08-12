"""Run and report the live Feature 4 existing-data retrieval demonstration.

This application service reuses Feature 4 retrieval and reports only collection
provenance and raw counts. It must not invoke an Actor or perform Feature 2
mapping, deduplication, location cleaning, or canonical processing.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apify_client import ApifyClient

from skill_compass.collection.apify_client import ApifyCollectionError
from skill_compass.collection.models import CapStatus
from skill_compass.collection.search_scopes import (
    DEFAULT_SEARCH_SCOPES_PATH,
    SearchScopeConfig,
)
from skill_compass.collection.seek_adapter import (
    SeekCollectionConfigurationError,
    load_seek_collection_config,
)
from skill_compass.config.settings import CollectionConfigurationError
from skill_compass.services.fetch_backfill import (
    DEFAULT_BACKFILL_FETCH_ROOT,
    DEFAULT_SEEK_COLLECTION_PATH,
    BackfillFetchError,
    BackfillFetchResult,
    BackfillFetchStatus,
    ScopeFetchStatus,
    SupplementalDiscoveryStatus,
    build_successful_run_fetch_plan,
    fetch_full_backfill,
)

# =============================================================================
# Demonstration contracts and execution
# =============================================================================


@dataclass(frozen=True, slots=True)
class Feature4DemoResult:
    """Bundle fetched evidence with the configuration needed for safe reporting."""

    fetch: BackfillFetchResult
    search_config: SearchScopeConfig
    actor_id: str


def run_feature_4_demo(
    *,
    force: bool = False,
    search_scopes_path: Path = DEFAULT_SEARCH_SCOPES_PATH,
    actor_config_path: Path = DEFAULT_SEEK_COLLECTION_PATH,
    output_root: Path = DEFAULT_BACKFILL_FETCH_ROOT,
    dotenv_path: Path = Path(".env"),
    environ: Mapping[str, str] | None = None,
    client_factory: Callable[[str], Any] = ApifyClient,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    event_handler: Callable[[str], None] = lambda _message: None,
) -> Feature4DemoResult:
    """Fetch every successful existing dataset and retain raw occurrences."""
    plan = build_successful_run_fetch_plan(
        search_scopes_path=search_scopes_path,
        output_root=output_root,
    )
    actor_id = load_seek_collection_config(actor_config_path).actor_id
    fetch = fetch_full_backfill(
        plan=plan,
        force=force,
        include_all_successful_runs=True,
        supplemental_actor_id=actor_id,
        dotenv_path=dotenv_path,
        environ=environ,
        client_factory=client_factory,
        clock=clock,
        event_handler=event_handler,
    )
    return Feature4DemoResult(
        fetch=fetch,
        search_config=plan.search_config,
        actor_id=actor_id,
    )


# =============================================================================
# Collection-only demonstration reporting
# =============================================================================


def _scope_summary_lines(result: Feature4DemoResult) -> list[str]:
    """Summarize raw counts by safely interpreted Actor search scope type."""
    rows = result.fetch.supplemental_results
    dataset_counts = Counter(item.scope_type for item in rows)
    listing_counts = Counter(
        {
            scope_type: sum(
                item.returned_item_count
                for item in rows
                if item.scope_type == scope_type
                and item.fetch_status is ScopeFetchStatus.SUCCESS
            )
            for scope_type in ("state", "classification", "other", "unrecognised")
        }
    )
    labels = {
        "state": "State-level searches",
        "classification": "Classification searches",
        "other": "Other recognised searches",
        "unrecognised": "Unrecognised run inputs",
    }
    lines = [
        "COLLECTION-SCOPE SUMMARY",
        "-" * 79,
        f"{'Scope type':35} {'Datasets':>10} {'Raw listings':>15}",
    ]
    for scope_type in ("state", "classification", "other", "unrecognised"):
        lines.append(
            f"{labels[scope_type]:35} {dataset_counts[scope_type]:>10,} "
            f"{listing_counts[scope_type]:>15,}"
        )
    lines.extend(
        [
            "-" * 79,
            f"{'Total':35} {len(rows):>10,} "
            f"{sum(item.returned_item_count for item in rows if item.fetch_status is ScopeFetchStatus.SUCCESS):>15,}",
        ]
    )
    return lines


def _state_summary_lines(result: Feature4DemoResult) -> list[str]:
    """Aggregate by exact Actor search location, not individual listing location."""
    rows = result.fetch.supplemental_results
    lines = [
        "RAW LISTINGS BY SEARCH STATE",
        "-" * 79,
        f"{'State':38} {'Datasets':>10} {'Raw listings':>15}",
    ]
    total_datasets = 0
    total_listings = 0
    for state_code, location in result.search_config.locations.items():
        state_rows = [item for item in rows if item.state_code == state_code]
        listing_count = sum(
            item.returned_item_count
            for item in state_rows
            if item.fetch_status is ScopeFetchStatus.SUCCESS
        )
        total_datasets += len(state_rows)
        total_listings += listing_count
        lines.append(f"{location:38} {len(state_rows):>10,} {listing_count:>15,}")
    unrecognised = [item for item in rows if item.state_code is None]
    unrecognised_listings = sum(
        item.returned_item_count
        for item in unrecognised
        if item.fetch_status is ScopeFetchStatus.SUCCESS
    )
    total_datasets += len(unrecognised)
    total_listings += unrecognised_listings
    lines.extend(
        [
            f"{'UNRECOGNISED SEARCH LOCATION':38} "
            f"{len(unrecognised):>10,} {unrecognised_listings:>15,}",
            "-" * 79,
            f"{'Total':38} {total_datasets:>10,} {total_listings:>15,}",
            "",
            "These are raw search-occurrence counts, not unique jobs.",
            "No individual listing location was cleaned or normalised.",
        ]
    )
    return lines


def _dataset_lines(result: Feature4DemoResult) -> list[str]:
    """Show concise existing-run provenance without printing source payloads."""
    lines = [
        "DATASET RESULTS",
        "-" * 79,
        f"{'Run ID':24} {'State':8} {'Classification':24} {'Listings':>9} Status",
    ]
    for item in result.fetch.supplemental_results:
        lines.append(
            f"{item.run_id[:24]:24} {(item.state_code or 'N/A'):8} "
            f"{(item.classification_name or item.scope_type):24.24} "
            f"{item.returned_item_count:>9,} {item.fetch_status.value}"
        )
    if not result.fetch.supplemental_results:
        lines.append("None.")
    return lines


def render_feature_4_demo(result: Feature4DemoResult) -> str:
    """Render connection, retrieval, scope, state, cap, and hand-off evidence."""
    manifest = result.fetch.manifest
    rows = result.fetch.supplemental_results
    successful = [
        item for item in rows if item.fetch_status is ScopeFetchStatus.SUCCESS
    ]
    empty_count = sum(item.returned_item_count == 0 for item in successful)
    connection_success = (
        manifest.supplemental_discovery_status is SupplementalDiscoveryStatus.SUCCESS
    )
    retrieval_success = connection_success and manifest.failed_supplemental_count == 0
    overall_pass = manifest.status is BackfillFetchStatus.COMPLETE
    cap_rows = [
        item
        for item in rows
        if item.cap_status in {CapStatus.CAP_RISK, CapStatus.CONFIRMED_TRUNCATED}
    ]
    cap_lines = ["CAP-RISK DATASETS", "-" * 79]
    if cap_rows:
        cap_lines.append(f"{'Run ID':30} {'State':10} {'Listings':>10} Status")
        cap_lines.extend(
            f"{item.run_id[:30]:30} {(item.state_code or 'N/A'):10} "
            f"{item.returned_item_count:>10,} {item.cap_status.value}"
            for item in cap_rows
        )
    else:
        cap_lines.append("None.")
    cap_lines.extend(
        [
            "",
            f"{len(cap_rows)} datasets require further coverage review.",
            "CAP_RISK does not prove source truncation.",
        ]
    )

    header = [
        "=" * 79,
        "SKILL COMPASS — FEATURE 4 LIVE APIFY RETRIEVAL DEMONSTRATION",
        "=" * 79,
        "",
        "Mode:                         Existing Apify datasets only",
        f"Actor:                        {result.actor_id}",
        "Actor invocation:             NO",
        "New searches started:         0",
        "",
        "APIFY CONNECTION",
        "-" * 79,
        f"API authentication:           {'SUCCESS' if connection_success else 'FAILED'}",
        f"Actor access:                 {'SUCCESS' if connection_success else 'FAILED'}",
        f"Successful runs discovered:   {manifest.discovered_successful_run_count:,}",
        f"Distinct datasets discovered: {manifest.supplemental_dataset_count:,}",
        f"Duplicate dataset references: {manifest.excluded_discovered_run_count:,}",
        "",
        "DATA RETRIEVAL",
        "-" * 79,
        f"Datasets attempted:           {manifest.supplemental_dataset_count:,}",
        f"Datasets retrieved:           {manifest.successful_supplemental_count:,}",
        f"Datasets failed:              {manifest.failed_supplemental_count:,}",
        f"Empty datasets:               {empty_count:,}",
        "",
        f"Raw listings retrieved:       {manifest.raw_listing_count:,}",
        f"Combined JSONL rows:           {manifest.combined_jsonl_row_count:,}",
        f"Reconciliation:               {manifest.reconciliation_status}",
        "",
        "Duplicate removal:           NOT PERFORMED",
        "Canonical mapping:           NOT PERFORMED",
        "Cleaning:                    NOT PERFORMED",
        "",
        f"Backfill status:              {manifest.status.value}",
        "",
    ]
    conclusion = [
        "FEATURE 4 DEMONSTRATION RESULT",
        "-" * 79,
        f"Apify connection:             {'SUCCESS' if connection_success else 'FAILED'}",
        f"Existing-run discovery:       {'SUCCESS' if connection_success else 'FAILED'}",
        f"Dataset retrieval:            {'SUCCESS' if retrieval_success else 'FAILED'}",
        f"Raw-row reconciliation:       {manifest.reconciliation_status}",
        f"Overall result:               {'PASS' if overall_pass else 'FAIL'}",
        "",
        "National raw file:",
        str(result.fetch.national_raw_path),
        "",
        "Fetch manifest:",
        str(result.fetch.manifest_path),
        "",
        "Dataset provenance:",
        str(result.fetch.supplemental_results_path),
        "",
        f"Raw listings:                 {manifest.raw_listing_count:,}",
        "",
        "Duplicates have NOT been removed.",
        "Feature 2 owns canonical mapping, duplicate detection, location",
        "normalisation, survivor selection, and deterministic cleaning.",
    ]
    return "\n".join(
        [
            *header,
            *_scope_summary_lines(result),
            "",
            *_state_summary_lines(result),
            "",
            *_dataset_lines(result),
            "",
            *cap_lines,
            "",
            *conclusion,
        ]
    )


def run_feature_4_demo_command(
    *,
    force: bool,
    search_scopes_path: Path = DEFAULT_SEARCH_SCOPES_PATH,
    actor_config_path: Path = DEFAULT_SEEK_COLLECTION_PATH,
    output_root: Path = DEFAULT_BACKFILL_FETCH_ROOT,
    output: Callable[[str], None] = print,
) -> int:
    """Run the live read-only demonstration and report safe failures."""
    output("Actor invocation: NO")
    output("Mode: Existing Apify datasets only")
    try:
        result = run_feature_4_demo(
            force=force,
            search_scopes_path=search_scopes_path,
            actor_config_path=actor_config_path,
            output_root=output_root,
            event_handler=output,
        )
    except (
        ApifyCollectionError,
        BackfillFetchError,
        CollectionConfigurationError,
        SeekCollectionConfigurationError,
        OSError,
        ValueError,
    ) as error:
        output(f"Feature 4 demonstration failed safely: {error}")
        output("No Actor was invoked.")
        return 1
    output(render_feature_4_demo(result))
    return 0 if result.fetch.manifest.status is BackfillFetchStatus.COMPLETE else 1
