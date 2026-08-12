"""Fetch and concatenate configured existing Apify backfill datasets.

This application service preserves every raw occurrence and coordinates only
existing storage reads. It must never invoke an Actor, deduplicate, map, clean,
extract, classify, or automatically start Feature 2.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from apify_client import ApifyClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from skill_compass.collection.apify_client import ApifyCollectionError
from skill_compass.collection.apify_fetch import (
    iterate_existing_dataset,
    resolve_existing_dataset,
)
from skill_compass.collection.apify_run_discovery import (
    ExistingActorDataset,
    discover_successful_actor_datasets,
)
from skill_compass.collection.backfill_sources import (
    BackfillSourceManifest,
    BackfillSourceManifestError,
    BackfillSourceReference,
    load_backfill_source_manifest,
)
from skill_compass.collection.cap_assessment import assess_result_cap
from skill_compass.collection.models import CapStatus
from skill_compass.collection.search_scopes import (
    DEFAULT_SEARCH_SCOPES_PATH,
    SearchScope,
    SearchScopeConfig,
    build_search_scopes,
    load_search_scope_config,
)
from skill_compass.collection.seek_adapter import (
    SeekCollectionConfigurationError,
    load_seek_collection_config,
)
from skill_compass.config.settings import (
    ApifySettings,
    CollectionConfigurationError,
    load_apify_settings,
)

# =============================================================================
# Batch fetch contracts
# =============================================================================


DEFAULT_BACKFILL_FETCH_ROOT = Path("data/private/collections/fetched")
DEFAULT_SEEK_COLLECTION_PATH = Path("sources/apify_seek_current/collection.yaml")


class BackfillFetchStatus(StrEnum):
    """Describe whether the existing national raw fetch is complete and usable."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ScopeFetchStatus(StrEnum):
    """Describe one configured scope's latest local fetch outcome."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    MISSING = "MISSING"


class SupplementalDiscoveryStatus(StrEnum):
    """Describe whether optional existing-run discovery succeeded."""

    NOT_REQUESTED = "NOT_REQUESTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class FrozenModel(BaseModel):
    """Provide strict immutable behavior for private fetch audit contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class BackfillScopeFetchResult(FrozenModel):
    """Record provenance and outcome for one expected configured scope."""

    scope_id: str
    state_code: str
    scope_type: Literal["state", "classification"]
    classification_id: str | None = None
    classification_name: str | None = None
    run_id: str | None = None
    dataset_id: str | None = None
    returned_item_count: int = Field(default=0, ge=0)
    cap_status: CapStatus = CapStatus.UNKNOWN
    fetch_status: ScopeFetchStatus
    local_raw_path: Path | None = None
    error_code: str | None = None
    error_detail: str | None = None
    fetched_at: datetime | None = None

    @model_validator(mode="after")
    def validate_scope_result(self) -> BackfillScopeFetchResult:
        """Require internally consistent success and failure audit evidence."""
        if self.fetched_at is not None and self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at must be timezone-aware")
        if self.fetch_status is ScopeFetchStatus.SUCCESS:
            if self.dataset_id is None or self.local_raw_path is None:
                raise ValueError("successful fetch requires dataset ID and local path")
            if self.error_code is not None or self.error_detail is not None:
                raise ValueError("successful fetch must not contain error details")
        elif self.error_code is None:
            raise ValueError("unsuccessful scope requires an error code")
        return self


class SupplementalFetchResult(FrozenModel):
    """Record one additional successful Actor run's dataset fetch provenance."""

    supplemental_id: str = Field(pattern=r"^run_[a-z0-9_]+$")
    run_id: str
    dataset_id: str
    started_at: datetime
    returned_item_count: int = Field(default=0, ge=0)
    cap_status: CapStatus = CapStatus.UNKNOWN
    fetch_status: Literal[ScopeFetchStatus.SUCCESS, ScopeFetchStatus.FAILED]
    local_raw_path: Path | None = None
    error_code: str | None = None
    error_detail: str | None = None
    fetched_at: datetime

    @model_validator(mode="after")
    def validate_supplemental_result(self) -> SupplementalFetchResult:
        """Require complete, timezone-aware supplemental fetch evidence."""
        if self.started_at.tzinfo is None or self.fetched_at.tzinfo is None:
            raise ValueError("supplemental timestamps must be timezone-aware")
        if self.fetch_status is ScopeFetchStatus.SUCCESS:
            if self.local_raw_path is None:
                raise ValueError("successful supplemental fetch requires a local path")
            if self.error_code is not None or self.error_detail is not None:
                raise ValueError("successful supplemental fetch cannot contain errors")
        elif self.error_code is None:
            raise ValueError("failed supplemental fetch requires an error code")
        return self


class BackfillFetchManifest(FrozenModel):
    """Record batch-level reconciliation without claiming a unique population."""

    backfill_id: str
    profile_code: str
    collection_strategy_version: str
    source_manifest_path: Path
    created_at: datetime
    updated_at: datetime
    status: BackfillFetchStatus
    expected_scope_count: int = Field(ge=0)
    supplied_dataset_count: int = Field(ge=0)
    successful_scope_count: int = Field(ge=0)
    failed_scope_count: int = Field(ge=0)
    missing_scope_count: int = Field(ge=0)
    supplemental_discovery_status: SupplementalDiscoveryStatus
    supplemental_actor_id: str | None = None
    discovered_successful_run_count: int = Field(ge=0)
    excluded_discovered_run_count: int = Field(ge=0)
    supplemental_dataset_count: int = Field(ge=0)
    successful_supplemental_count: int = Field(ge=0)
    failed_supplemental_count: int = Field(ge=0)
    configured_raw_listing_count: int = Field(ge=0)
    supplemental_raw_listing_count: int = Field(ge=0)
    raw_listing_count: int = Field(ge=0)
    combined_jsonl_row_count: int = Field(ge=0)
    cap_risk_scope_count: int = Field(ge=0)
    reconciliation_status: Literal["PASS", "FAIL"]
    national_raw_path: Path
    scope_results_path: Path
    supplemental_results_path: Path | None = None
    supplemental_discovery_error_code: str | None = None
    supplemental_discovery_error_detail: str | None = None
    actor_invocation: Literal[False] = False
    duplicate_removal: Literal["DEFERRED_TO_FEATURE_2"] = "DEFERRED_TO_FEATURE_2"

    @model_validator(mode="after")
    def validate_manifest(self) -> BackfillFetchManifest:
        """Require aware times and exact successful raw-row reconciliation."""
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("fetch manifest timestamps must be timezone-aware")
        if self.raw_listing_count != self.combined_jsonl_row_count:
            if self.reconciliation_status != "FAIL":
                raise ValueError("unequal raw counts require FAIL reconciliation")
        elif self.reconciliation_status != "PASS":
            raise ValueError("equal raw counts require PASS reconciliation")
        if (
            self.successful_scope_count
            + self.failed_scope_count
            + self.missing_scope_count
            != self.expected_scope_count
        ):
            raise ValueError("scope outcome counts must reconcile to expected scopes")
        if (
            self.successful_supplemental_count + self.failed_supplemental_count
            != self.supplemental_dataset_count
        ):
            raise ValueError("supplemental outcome counts must reconcile")
        if (
            self.configured_raw_listing_count + self.supplemental_raw_listing_count
            != self.raw_listing_count
        ):
            raise ValueError("configured and supplemental raw counts must reconcile")
        if self.supplemental_discovery_status is SupplementalDiscoveryStatus.FAILED:
            if self.supplemental_discovery_error_code is None:
                raise ValueError("failed supplemental discovery requires an error code")
        elif (
            self.supplemental_discovery_error_code is not None
            or self.supplemental_discovery_error_detail is not None
        ):
            raise ValueError("successful discovery cannot contain discovery errors")
        return self


@dataclass(frozen=True, slots=True)
class BackfillFetchPlan:
    """Bundle authoritative scopes and validated existing source references."""

    search_config: SearchScopeConfig
    scopes: tuple[SearchScope, ...]
    source_manifest: BackfillSourceManifest
    output_root: Path
    backfill_id: str


@dataclass(frozen=True, slots=True)
class BackfillFetchResult:
    """Return all final persisted paths and typed reconciliation evidence."""

    manifest: BackfillFetchManifest
    scope_results: tuple[BackfillScopeFetchResult, ...]
    supplemental_results: tuple[SupplementalFetchResult, ...]
    backfill_dir: Path
    manifest_path: Path
    scope_results_path: Path
    supplemental_results_path: Path | None
    national_raw_path: Path


class BackfillFetchError(RuntimeError):
    """Report a fatal configuration, audit, or reconciliation failure."""


# =============================================================================
# Plan construction and stable private output identity
# =============================================================================


def _safe_slug(value: str) -> str:
    """Create one stable filename-safe identifier from a private manifest stem."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    if not slug:
        raise BackfillFetchError(
            "source manifest filename cannot produce a backfill ID"
        )
    return slug


def build_backfill_fetch_plan(
    *,
    source_manifest_path: Path,
    search_scopes_path: Path = DEFAULT_SEARCH_SCOPES_PATH,
    output_root: Path = DEFAULT_BACKFILL_FETCH_ROOT,
) -> BackfillFetchPlan:
    """Validate the private references against every authoritative active scope."""
    search_config = load_search_scope_config(search_scopes_path)
    scopes = build_search_scopes(search_config)
    source_manifest = load_backfill_source_manifest(
        source_manifest_path, configured_scopes=scopes
    )
    backfill_id = (
        f"{search_config.profile_code}_"
        f"{search_config.collection_strategy_version.replace('.', '_')}_"
        f"{_safe_slug(source_manifest_path.stem)}"
    )
    return BackfillFetchPlan(
        search_config=search_config,
        scopes=scopes,
        source_manifest=source_manifest,
        output_root=output_root,
        backfill_id=backfill_id,
    )


# =============================================================================
# Atomic audit and raw file persistence
# =============================================================================


_SCOPE_RESULT_FIELDS = tuple(BackfillScopeFetchResult.model_fields)
_SUPPLEMENTAL_RESULT_FIELDS = tuple(SupplementalFetchResult.model_fields)


def _write_text_atomic(path: Path, content: str) -> None:
    """Replace one local audit only after its complete content is written."""
    partial_path = path.with_suffix(path.suffix + ".partial")
    partial_path.write_text(content, encoding="utf-8")
    partial_path.replace(path)


def _scope_csv_row(result: BackfillScopeFetchResult) -> dict[str, str | int]:
    """Serialize a typed scope result into stable scalar CSV values."""
    document = result.model_dump(mode="json")
    return {
        name: "" if document[name] is None else document[name]
        for name in _SCOPE_RESULT_FIELDS
    }


def _write_scope_results(
    path: Path,
    *,
    scopes: tuple[SearchScope, ...],
    results: Mapping[str, BackfillScopeFetchResult],
) -> None:
    """Persist one ordered row per expected scope after every fetch attempt."""
    partial_path = path.with_suffix(path.suffix + ".partial")
    with partial_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=_SCOPE_RESULT_FIELDS)
        writer.writeheader()
        for scope in scopes:
            writer.writerow(_scope_csv_row(results[scope.scope_id]))
    partial_path.replace(path)


def _load_scope_results(path: Path) -> dict[str, BackfillScopeFetchResult]:
    """Restore valid previous outcomes for default skip and retry behavior."""
    if not path.exists():
        return {}
    results: dict[str, BackfillScopeFetchResult] = {}
    try:
        with path.open(encoding="utf-8", newline="") as input_file:
            for row in csv.DictReader(input_file):
                normalized = {
                    key: value if value != "" else None for key, value in row.items()
                }
                result = BackfillScopeFetchResult.model_validate(normalized)
                results[result.scope_id] = result
    except (OSError, csv.Error, ValidationError) as error:
        raise BackfillFetchError(
            f"existing scope_results.csv could not be validated: {path}"
        ) from error
    return results


def _write_supplemental_results(
    path: Path, results: tuple[SupplementalFetchResult, ...]
) -> None:
    """Persist supplemental provenance in deterministic discovery order."""
    partial_path = path.with_suffix(path.suffix + ".partial")
    with partial_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=_SUPPLEMENTAL_RESULT_FIELDS,
        )
        writer.writeheader()
        for result in results:
            document = result.model_dump(mode="json")
            writer.writerow(
                {
                    name: "" if document[name] is None else document[name]
                    for name in _SUPPLEMENTAL_RESULT_FIELDS
                }
            )
    partial_path.replace(path)


def _load_supplemental_results(
    path: Path,
) -> dict[str, SupplementalFetchResult]:
    """Restore previous supplemental outcomes for skip and retry behavior."""
    if not path.exists():
        return {}
    results: dict[str, SupplementalFetchResult] = {}
    try:
        with path.open(encoding="utf-8", newline="") as input_file:
            for row in csv.DictReader(input_file):
                normalized = {
                    key: value if value != "" else None for key, value in row.items()
                }
                result = SupplementalFetchResult.model_validate(normalized)
                results[result.run_id] = result
    except (OSError, csv.Error, ValidationError) as error:
        raise BackfillFetchError(
            f"existing supplemental_results.csv could not be validated: {path}"
        ) from error
    return results


def _missing_result(scope: SearchScope) -> BackfillScopeFetchResult:
    """Represent an expected configured scope absent from the private source CSV."""
    return BackfillScopeFetchResult(
        scope_id=scope.scope_id,
        state_code=scope.state_code,
        scope_type=("classification" if scope.classification_id else "state"),
        classification_id=scope.classification_id,
        classification_name=scope.classification_name,
        fetch_status=ScopeFetchStatus.MISSING,
        cap_status=CapStatus.UNKNOWN,
        error_code="MISSING_SOURCE_REFERENCE",
        error_detail="No run_id or dataset_id row was supplied for this scope.",
    )


def _safe_error_detail(error: Exception, token: str) -> str:
    """Bound and redact external failure details before terminal or disk output."""
    return f"{type(error).__name__}: {error}".replace(token, "[REDACTED]")[:500]


def _fetch_scope(
    *,
    scope: SearchScope,
    reference: BackfillSourceReference,
    scope_path: Path,
    settings: ApifySettings,
    shared_client: Any,
    cap_warning_threshold: int,
    fetched_at: datetime,
) -> BackfillScopeFetchResult:
    """Resolve and stream every existing dataset item without an Actor client."""
    resolved = resolve_existing_dataset(
        settings=settings,
        dataset_id=reference.dataset_id,
        run_id=(None if reference.dataset_id is not None else reference.run_id),
        client_factory=lambda _token: shared_client,
    )
    partial_path = scope_path.with_suffix(scope_path.suffix + ".partial")
    returned_count = 0
    try:
        with partial_path.open("w", encoding="utf-8", newline="\n") as output_file:
            for item in iterate_existing_dataset(resolved):
                output_file.write(
                    json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                )
                output_file.write("\n")
                returned_count += 1
        partial_path.replace(scope_path)
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise

    cap = assess_result_cap(
        returned_item_count=returned_count,
        warning_threshold=cap_warning_threshold,
    )
    return BackfillScopeFetchResult(
        scope_id=scope.scope_id,
        state_code=scope.state_code,
        scope_type=("classification" if scope.classification_id else "state"),
        classification_id=scope.classification_id,
        classification_name=scope.classification_name,
        run_id=resolved.run_id or reference.run_id,
        dataset_id=resolved.dataset_id,
        returned_item_count=returned_count,
        cap_status=cap.status,
        fetch_status=ScopeFetchStatus.SUCCESS,
        local_raw_path=scope_path.resolve(),
        fetched_at=fetched_at,
    )


def _failed_result(
    *,
    scope: SearchScope,
    reference: BackfillSourceReference,
    error: Exception,
    token: str,
    fetched_at: datetime,
) -> BackfillScopeFetchResult:
    """Record a safe per-scope failure while preserving supplied provenance."""
    return BackfillScopeFetchResult(
        scope_id=scope.scope_id,
        state_code=scope.state_code,
        scope_type=("classification" if scope.classification_id else "state"),
        classification_id=scope.classification_id,
        classification_name=scope.classification_name,
        run_id=reference.run_id,
        dataset_id=reference.dataset_id,
        fetch_status=ScopeFetchStatus.FAILED,
        cap_status=CapStatus.UNKNOWN,
        error_code=type(error).__name__,
        error_detail=_safe_error_detail(error, token),
        fetched_at=fetched_at,
    )


def _supplemental_id(run_id: str) -> str:
    """Create a stable safe local ID from one validated Apify run ID."""
    normalized = re.sub(r"[^a-z0-9]+", "_", run_id.casefold()).strip("_")
    if not normalized:
        raise BackfillFetchError("supplemental run ID cannot produce a local ID")
    return f"run_{normalized}"


def _fetch_supplemental_dataset(
    *,
    discovered: ExistingActorDataset,
    raw_path: Path,
    settings: ApifySettings,
    shared_client: Any,
    cap_warning_threshold: int,
    fetched_at: datetime,
) -> SupplementalFetchResult:
    """Stream every item from one discovered existing default dataset."""
    resolved = resolve_existing_dataset(
        settings=settings,
        dataset_id=discovered.dataset_id,
        client_factory=lambda _token: shared_client,
    )
    partial_path = raw_path.with_suffix(raw_path.suffix + ".partial")
    returned_count = 0
    try:
        with partial_path.open("w", encoding="utf-8", newline="\n") as output_file:
            for item in iterate_existing_dataset(resolved):
                output_file.write(
                    json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                )
                output_file.write("\n")
                returned_count += 1
        partial_path.replace(raw_path)
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise

    cap = assess_result_cap(
        returned_item_count=returned_count,
        warning_threshold=cap_warning_threshold,
    )
    return SupplementalFetchResult(
        supplemental_id=_supplemental_id(discovered.run_id),
        run_id=discovered.run_id,
        dataset_id=discovered.dataset_id,
        started_at=discovered.started_at,
        returned_item_count=returned_count,
        cap_status=cap.status,
        fetch_status=ScopeFetchStatus.SUCCESS,
        local_raw_path=raw_path.resolve(),
        fetched_at=fetched_at,
    )


def _failed_supplemental_result(
    *,
    discovered: ExistingActorDataset,
    error: Exception,
    token: str,
    fetched_at: datetime,
) -> SupplementalFetchResult:
    """Record one safe discovered-dataset failure without stopping later fetches."""
    return SupplementalFetchResult(
        supplemental_id=_supplemental_id(discovered.run_id),
        run_id=discovered.run_id,
        dataset_id=discovered.dataset_id,
        started_at=discovered.started_at,
        fetch_status=ScopeFetchStatus.FAILED,
        error_code=type(error).__name__,
        error_detail=_safe_error_detail(error, token),
        fetched_at=fetched_at,
    )


# =============================================================================
# Raw occurrence-preserving national concatenation
# =============================================================================


def combine_successful_scope_files(
    *,
    national_raw_path: Path,
    scopes: tuple[SearchScope, ...],
    results: Mapping[str, BackfillScopeFetchResult],
    supplemental_results: tuple[SupplementalFetchResult, ...] = (),
) -> int:
    """Concatenate configured then supplemental occurrences without deduplication."""
    partial_path = national_raw_path.with_suffix(national_raw_path.suffix + ".partial")
    combined_rows = 0
    with partial_path.open("w", encoding="utf-8", newline="\n") as national_file:
        for scope in scopes:
            result = results[scope.scope_id]
            if result.fetch_status is not ScopeFetchStatus.SUCCESS:
                continue
            if result.local_raw_path is None:
                raise BackfillFetchError(
                    f"successful scope has no local path: {scope.scope_id}"
                )
            with result.local_raw_path.open(encoding="utf-8") as scope_file:
                for line in scope_file:
                    national_file.write(line.rstrip("\r\n") + "\n")
                    combined_rows += 1
        for result in supplemental_results:
            if result.fetch_status is not ScopeFetchStatus.SUCCESS:
                continue
            if result.local_raw_path is None:
                raise BackfillFetchError(
                    f"successful supplemental run has no local path: {result.run_id}"
                )
            with result.local_raw_path.open(encoding="utf-8") as supplemental_file:
                for line in supplemental_file:
                    national_file.write(line.rstrip("\r\n") + "\n")
                    combined_rows += 1
    partial_path.replace(national_raw_path)
    return combined_rows


def _build_batch_manifest(
    *,
    plan: BackfillFetchPlan,
    results: Mapping[str, BackfillScopeFetchResult],
    supplemental_results: tuple[SupplementalFetchResult, ...],
    supplemental_discovery_status: SupplementalDiscoveryStatus,
    supplemental_actor_id: str | None,
    discovered_successful_run_count: int,
    excluded_discovered_run_count: int,
    supplemental_discovery_error: Exception | None,
    token: str,
    created_at: datetime,
    updated_at: datetime,
    national_raw_path: Path,
    scope_results_path: Path,
    supplemental_results_path: Path | None,
    combined_rows: int,
) -> BackfillFetchManifest:
    """Derive national status and reconciliation strictly from scope outcomes."""
    successful = [
        result
        for result in results.values()
        if result.fetch_status is ScopeFetchStatus.SUCCESS
    ]
    failed_count = sum(
        result.fetch_status is ScopeFetchStatus.FAILED for result in results.values()
    )
    missing_count = sum(
        result.fetch_status is ScopeFetchStatus.MISSING for result in results.values()
    )
    successful_supplemental = [
        result
        for result in supplemental_results
        if result.fetch_status is ScopeFetchStatus.SUCCESS
    ]
    failed_supplemental_count = sum(
        result.fetch_status is ScopeFetchStatus.FAILED
        for result in supplemental_results
    )
    configured_raw_listing_count = sum(
        result.returned_item_count for result in successful
    )
    supplemental_raw_listing_count = sum(
        result.returned_item_count for result in successful_supplemental
    )
    raw_listing_count = configured_raw_listing_count + supplemental_raw_listing_count
    cap_risk_count = sum(
        result.cap_status in {CapStatus.CAP_RISK, CapStatus.CONFIRMED_TRUNCATED}
        for result in [*successful, *successful_supplemental]
    )
    configured_complete = len(successful) == len(plan.scopes)
    supplemental_complete = (
        supplemental_discovery_status is not SupplementalDiscoveryStatus.FAILED
        and failed_supplemental_count == 0
    )
    if configured_complete and supplemental_complete:
        status = BackfillFetchStatus.COMPLETE
    elif successful or successful_supplemental:
        status = BackfillFetchStatus.PARTIAL
    else:
        status = BackfillFetchStatus.FAILED
    reconciliation = "PASS" if raw_listing_count == combined_rows else "FAIL"
    return BackfillFetchManifest(
        backfill_id=plan.backfill_id,
        profile_code=plan.search_config.profile_code,
        collection_strategy_version=plan.search_config.collection_strategy_version,
        source_manifest_path=plan.source_manifest.path.resolve(),
        created_at=created_at,
        updated_at=updated_at,
        status=status,
        expected_scope_count=len(plan.scopes),
        supplied_dataset_count=len(plan.source_manifest.references),
        successful_scope_count=len(successful),
        failed_scope_count=failed_count,
        missing_scope_count=missing_count,
        supplemental_discovery_status=supplemental_discovery_status,
        supplemental_actor_id=supplemental_actor_id,
        discovered_successful_run_count=discovered_successful_run_count,
        excluded_discovered_run_count=excluded_discovered_run_count,
        supplemental_dataset_count=len(supplemental_results),
        successful_supplemental_count=len(successful_supplemental),
        failed_supplemental_count=failed_supplemental_count,
        configured_raw_listing_count=configured_raw_listing_count,
        supplemental_raw_listing_count=supplemental_raw_listing_count,
        raw_listing_count=raw_listing_count,
        combined_jsonl_row_count=combined_rows,
        cap_risk_scope_count=cap_risk_count,
        reconciliation_status=reconciliation,
        national_raw_path=national_raw_path.resolve(),
        scope_results_path=scope_results_path.resolve(),
        supplemental_results_path=(
            supplemental_results_path.resolve()
            if supplemental_results_path is not None
            else None
        ),
        supplemental_discovery_error_code=(
            type(supplemental_discovery_error).__name__
            if supplemental_discovery_error is not None
            else None
        ),
        supplemental_discovery_error_detail=(
            _safe_error_detail(supplemental_discovery_error, token)
            if supplemental_discovery_error is not None
            else None
        ),
        actor_invocation=False,
        duplicate_removal="DEFERRED_TO_FEATURE_2",
    )


# =============================================================================
# Resumable sequential existing-dataset fetch
# =============================================================================


def fetch_full_backfill(
    *,
    plan: BackfillFetchPlan,
    force: bool = False,
    include_all_successful_runs: bool = False,
    supplemental_actor_id: str | None = None,
    dotenv_path: Path = Path(".env"),
    environ: Mapping[str, str] | None = None,
    client_factory: Callable[[str], Any] = ApifyClient,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    event_handler: Callable[[str], None] = lambda _message: None,
) -> BackfillFetchResult:
    """Fetch all supplied scopes sequentially and preserve every raw occurrence."""
    created_at = clock()
    if created_at.tzinfo is None:
        raise ValueError("fetch clock must return a timezone-aware datetime")
    backfill_dir = plan.output_root / plan.backfill_id
    scopes_dir = backfill_dir / "scopes"
    scopes_dir.mkdir(parents=True, exist_ok=True)
    scope_results_path = backfill_dir / "scope_results.csv"
    supplemental_results_path = (
        backfill_dir / "supplemental_results.csv"
        if include_all_successful_runs
        else None
    )
    manifest_path = backfill_dir / "fetch_manifest.json"
    national_raw_path = backfill_dir / "national_jobs_raw.jsonl"

    previous_results = _load_scope_results(scope_results_path)
    references_by_id = {
        reference.scope_id: reference for reference in plan.source_manifest.references
    }
    results = {scope.scope_id: _missing_result(scope) for scope in plan.scopes}
    results.update(
        {
            scope_id: result
            for scope_id, result in previous_results.items()
            if scope_id in results
        }
    )

    settings = load_apify_settings(dotenv_path=dotenv_path, environ=environ)
    token = settings.token.get_secret_value()
    shared_client = client_factory(token)

    for scope in plan.scopes:
        reference = references_by_id.get(scope.scope_id)
        if reference is None:
            results[scope.scope_id] = _missing_result(scope)
            event_handler(f"[MISSING] {scope.scope_id} — no source reference")
            continue

        previous = results[scope.scope_id]
        expected_scope_path = scopes_dir / f"{scope.scope_id}.jsonl"
        if (
            not force
            and previous.fetch_status is ScopeFetchStatus.SUCCESS
            and (
                (
                    reference.dataset_id is not None
                    and previous.dataset_id == reference.dataset_id
                )
                or (
                    reference.dataset_id is None and previous.run_id == reference.run_id
                )
            )
            and previous.local_raw_path == expected_scope_path.resolve()
            and expected_scope_path.exists()
        ):
            event_handler(f"[SKIP] {scope.scope_id} — already fetched")
            continue
        if previous.fetch_status is ScopeFetchStatus.FAILED:
            event_handler(f"[RETRY] {scope.scope_id} — previous fetch failed")
        else:
            event_handler(f"[FETCH] {scope.scope_id}")

        try:
            results[scope.scope_id] = _fetch_scope(
                scope=scope,
                reference=reference,
                scope_path=expected_scope_path,
                settings=settings,
                shared_client=shared_client,
                cap_warning_threshold=plan.search_config.cap_warning_threshold,
                fetched_at=clock(),
            )
        except Exception as error:
            results[scope.scope_id] = _failed_result(
                scope=scope,
                reference=reference,
                error=error,
                token=token,
                fetched_at=clock(),
            )
            event_handler(f"[FAILED] {scope.scope_id} — recorded; continuing")
        _write_scope_results(scope_results_path, scopes=plan.scopes, results=results)

    _write_scope_results(scope_results_path, scopes=plan.scopes, results=results)

    supplemental_results: tuple[SupplementalFetchResult, ...] = ()
    discovery_status = SupplementalDiscoveryStatus.NOT_REQUESTED
    discovery_error: Exception | None = None
    discovered_count = 0
    excluded_count = 0
    if include_all_successful_runs:
        assert supplemental_results_path is not None
        supplemental_dir = backfill_dir / "supplemental"
        supplemental_dir.mkdir(parents=True, exist_ok=True)
        previous_supplemental = _load_supplemental_results(supplemental_results_path)
        discovery_status = SupplementalDiscoveryStatus.SUCCESS
        if supplemental_actor_id is None:
            discovery_status = SupplementalDiscoveryStatus.FAILED
            discovery_error = BackfillFetchError(
                "supplemental actor ID is required for successful-run discovery"
            )
        else:
            try:
                discovered = discover_successful_actor_datasets(
                    client=shared_client,
                    actor_id=supplemental_actor_id,
                )
                discovered_count = len(discovered)
            except Exception as error:
                discovery_status = SupplementalDiscoveryStatus.FAILED
                discovery_error = error
                discovered = ()
                event_handler("[DISCOVERY FAILED] recorded; no Actor was invoked")

        if discovery_status is SupplementalDiscoveryStatus.FAILED:
            supplemental_results = tuple(
                sorted(
                    (
                        result
                        for result in previous_supplemental.values()
                        if result.fetch_status is ScopeFetchStatus.FAILED
                        or (
                            result.local_raw_path is not None
                            and result.local_raw_path.exists()
                        )
                    ),
                    key=lambda result: (result.started_at, result.run_id),
                )
            )
        else:
            manifest_run_ids = {
                reference.run_id
                for reference in plan.source_manifest.references
                if reference.run_id is not None
            }
            represented_dataset_ids = {
                reference.dataset_id
                for reference in plan.source_manifest.references
                if reference.dataset_id is not None
            }
            represented_dataset_ids.update(
                result.dataset_id
                for result in results.values()
                if result.dataset_id is not None
            )
            candidates: list[ExistingActorDataset] = []
            for item in discovered:
                if (
                    item.run_id in manifest_run_ids
                    or item.dataset_id in represented_dataset_ids
                ):
                    excluded_count += 1
                    continue
                represented_dataset_ids.add(item.dataset_id)
                candidates.append(item)

            supplemental_by_run: dict[str, SupplementalFetchResult] = {}
            for item in candidates:
                expected_path = (
                    supplemental_dir / f"{_supplemental_id(item.run_id)}.jsonl"
                )
                previous = previous_supplemental.get(item.run_id)
                if (
                    not force
                    and previous is not None
                    and previous.fetch_status is ScopeFetchStatus.SUCCESS
                    and previous.dataset_id == item.dataset_id
                    and previous.local_raw_path == expected_path.resolve()
                    and expected_path.exists()
                ):
                    supplemental_by_run[item.run_id] = previous
                    event_handler(f"[SKIP EXTRA] {item.run_id} — already fetched")
                    continue
                if (
                    previous is not None
                    and previous.fetch_status is ScopeFetchStatus.FAILED
                ):
                    event_handler(
                        f"[RETRY EXTRA] {item.run_id} — previous fetch failed"
                    )
                else:
                    event_handler(f"[FETCH EXTRA] {item.run_id}")
                try:
                    supplemental_by_run[item.run_id] = _fetch_supplemental_dataset(
                        discovered=item,
                        raw_path=expected_path,
                        settings=settings,
                        shared_client=shared_client,
                        cap_warning_threshold=(
                            plan.search_config.cap_warning_threshold
                        ),
                        fetched_at=clock(),
                    )
                except Exception as error:
                    supplemental_by_run[item.run_id] = _failed_supplemental_result(
                        discovered=item,
                        error=error,
                        token=token,
                        fetched_at=clock(),
                    )
                    event_handler(
                        f"[FAILED EXTRA] {item.run_id} — recorded; continuing"
                    )
                supplemental_results = tuple(
                    supplemental_by_run[candidate.run_id]
                    for candidate in candidates
                    if candidate.run_id in supplemental_by_run
                )
                _write_supplemental_results(
                    supplemental_results_path,
                    supplemental_results,
                )
            supplemental_results = tuple(
                supplemental_by_run[candidate.run_id] for candidate in candidates
            )
        _write_supplemental_results(
            supplemental_results_path,
            supplemental_results,
        )

    combined_rows = combine_successful_scope_files(
        national_raw_path=national_raw_path,
        scopes=plan.scopes,
        results=results,
        supplemental_results=supplemental_results,
    )
    batch_manifest = _build_batch_manifest(
        plan=plan,
        results=results,
        supplemental_results=supplemental_results,
        supplemental_discovery_status=discovery_status,
        supplemental_actor_id=supplemental_actor_id,
        discovered_successful_run_count=discovered_count,
        excluded_discovered_run_count=excluded_count,
        supplemental_discovery_error=discovery_error,
        token=token,
        created_at=created_at,
        updated_at=clock(),
        national_raw_path=national_raw_path,
        scope_results_path=scope_results_path,
        supplemental_results_path=supplemental_results_path,
        combined_rows=combined_rows,
    )
    _write_text_atomic(manifest_path, batch_manifest.model_dump_json(indent=2) + "\n")
    if batch_manifest.reconciliation_status != "PASS":
        raise BackfillFetchError(
            "per-scope listing counts do not reconcile to national JSONL rows"
        )
    ordered_results = tuple(results[scope.scope_id] for scope in plan.scopes)
    return BackfillFetchResult(
        manifest=batch_manifest,
        scope_results=ordered_results,
        supplemental_results=supplemental_results,
        backfill_dir=backfill_dir,
        manifest_path=manifest_path,
        scope_results_path=scope_results_path,
        supplemental_results_path=supplemental_results_path,
        national_raw_path=national_raw_path,
    )


# =============================================================================
# Shared dry-run and terminal reporting
# =============================================================================


def render_backfill_fetch_dry_run(
    plan: BackfillFetchPlan,
    *,
    include_all_successful_runs: bool = False,
    supplemental_actor_id: str | None = None,
) -> str:
    """Report manifest readiness without loading a token or constructing a client."""
    supplied_scope_ids = {item.scope_id for item in plan.source_manifest.references}
    missing_lines = (
        "\n".join(plan.source_manifest.missing_scope_ids)
        if plan.source_manifest.missing_scope_ids
        else "None."
    )
    return "\n".join(
        [
            "=" * 79,
            "SKILL COMPASS — EXISTING APIFY BACKFILL MANIFEST VALIDATION",
            "=" * 79,
            "",
            "Actor invocation: NO",
            "Mode: Existing Apify datasets only",
            f"Profile: {plan.search_config.profile_code.replace('_', ' ').title()}",
            "",
            f"Expected scopes: {len(plan.scopes)}",
            f"Supplied datasets: {len(supplied_scope_ids)}",
            f"Missing scopes: {len(plan.source_manifest.missing_scope_ids)}",
            "Invalid scopes: 0",
            f"Manifest ready: {'YES' if plan.source_manifest.is_ready else 'NO'}",
            f"Supplemental discovery: "
            f"{'REQUESTED' if include_all_successful_runs else 'NOT REQUESTED'}",
            f"Supplemental Actor: {supplemental_actor_id or 'N/A'}",
            "",
            "MISSING SCOPES",
            "-" * 79,
            missing_lines,
            "",
            "DRY RUN ONLY",
            "Successful-run discovery was not executed.",
            "No Apify API request made.",
            "No Actor was invoked.",
        ]
    )


def render_backfill_fetch_summary(result: BackfillFetchResult) -> str:
    """Report every scope, cap risk, reconciliation, and the Feature 2 hand-off."""
    manifest = result.manifest
    per_scope_lines = ["SCOPE RESULTS", "-" * 79]
    per_scope_lines.append(f"{'Scope':48} {'Listings':>10}    Status")
    per_scope_lines.extend(
        f"{item.scope_id:48} {item.returned_item_count:>10,}    "
        f"{item.fetch_status.value}"
        for item in result.scope_results
    )

    cap_results = [
        item
        for item in result.scope_results
        if item.cap_status in {CapStatus.CAP_RISK, CapStatus.CONFIRMED_TRUNCATED}
    ]
    supplemental_cap_results = [
        item
        for item in result.supplemental_results
        if item.cap_status in {CapStatus.CAP_RISK, CapStatus.CONFIRMED_TRUNCATED}
    ]
    cap_lines = ["CAP-RISK SCOPES", "-" * 79]
    if cap_results:
        cap_lines.append(f"{'Scope':48} {'Listings':>10}    Status")
        cap_lines.extend(
            f"{item.scope_id:48} {item.returned_item_count:>10,}    "
            f"{item.cap_status.value}"
            for item in cap_results
        )
        cap_lines.extend(
            f"{'extra:' + item.run_id:48} {item.returned_item_count:>10,}    "
            f"{item.cap_status.value}"
            for item in supplemental_cap_results
        )
    else:
        if supplemental_cap_results:
            cap_lines.append(f"{'Scope':48} {'Listings':>10}    Status")
            cap_lines.extend(
                f"{'extra:' + item.run_id:48} "
                f"{item.returned_item_count:>10,}    {item.cap_status.value}"
                for item in supplemental_cap_results
            )
        else:
            cap_lines.append("None.")
    cap_lines.extend(
        [
            "",
            f"{len(cap_results) + len(supplemental_cap_results)} datasets require "
            "further review or partitioning.",
        ]
    )

    summary_lines = [
        "=" * 79,
        "SKILL COMPASS — EXISTING APIFY NATIONAL BACKFILL FETCH",
        "=" * 79,
        "",
        "Actor invocation:             NO",
        "Mode:                         Existing Apify datasets only",
        f"Profile:                      "
        f"{manifest.profile_code.replace('_', ' ').title()}",
        "",
        "BACKFILL FETCH SUMMARY",
        "-" * 79,
        f"Total scopes expected:       {manifest.expected_scope_count}",
        f"Datasets in manifest:        {manifest.supplied_dataset_count}",
        f"Datasets fetched:            {manifest.successful_scope_count}",
        f"Successful:                  {manifest.successful_scope_count}",
        f"Failed:                      {manifest.failed_scope_count}",
        f"Missing:                     {manifest.missing_scope_count}",
        "",
        f"Successful-run discovery:   {manifest.supplemental_discovery_status.value}",
        f"Successful runs discovered: {manifest.discovered_successful_run_count}",
        f"Already represented:        {manifest.excluded_discovered_run_count}",
        f"Supplemental datasets:      {manifest.supplemental_dataset_count}",
        f"Supplemental successful:    {manifest.successful_supplemental_count}",
        f"Supplemental failed:        {manifest.failed_supplemental_count}",
        "",
        f"Configured raw listings:    {manifest.configured_raw_listing_count:,}",
        f"Supplemental raw listings:  {manifest.supplemental_raw_listing_count:,}",
        f"Raw listings fetched:        {manifest.raw_listing_count:,}",
        f"Listings written:            {manifest.combined_jsonl_row_count:,}",
        f"Reconciliation:              {manifest.reconciliation_status}",
        "",
        "Duplicate removal:           DEFERRED TO FEATURE 2",
        "",
        f"Backfill status:             {manifest.status.value}",
        "",
        "Combined raw file:",
        str(result.national_raw_path),
        "",
    ]
    supplemental_lines = ["SUPPLEMENTAL DATASET RESULTS", "-" * 79]
    if result.supplemental_results:
        supplemental_lines.append(f"{'Run':48} {'Listings':>10}    Status")
        supplemental_lines.extend(
            f"{item.run_id:48} {item.returned_item_count:>10,}    "
            f"{item.fetch_status.value}"
            for item in result.supplemental_results
        )
    else:
        supplemental_lines.append("None.")
    handoff_lines = [
        "FEATURE 2 HAND-OFF",
        "-" * 79,
        "",
        "Raw national backfill is ready.",
        "",
        "Input:",
        str(result.national_raw_path),
        "",
        f"Raw listings: {manifest.combined_jsonl_row_count:,}",
        "",
        "Duplicates have NOT been removed.",
        "Feature 2 owns canonical identity validation, duplicate detection,",
        "survivor selection, and deterministic cleaning.",
        "Feature 2 was not run automatically.",
    ]
    return "\n".join(
        [
            *summary_lines,
            *per_scope_lines,
            "",
            *supplemental_lines,
            "",
            *cap_lines,
            "",
            *handoff_lines,
        ]
    )


def run_fetch_backfill_command(
    *,
    source_manifest_path: Path,
    dry_run: bool,
    force: bool,
    include_all_successful_runs: bool = False,
    actor_config_path: Path = DEFAULT_SEEK_COLLECTION_PATH,
    search_scopes_path: Path = DEFAULT_SEARCH_SCOPES_PATH,
    output_root: Path = DEFAULT_BACKFILL_FETCH_ROOT,
    output: Callable[[str], None] = print,
) -> int:
    """Share script/CLI validation and execution without duplicating business logic."""
    try:
        plan = build_backfill_fetch_plan(
            source_manifest_path=source_manifest_path,
            search_scopes_path=search_scopes_path,
            output_root=output_root,
        )
    except (
        BackfillSourceManifestError,
        BackfillFetchError,
        OSError,
        ValueError,
    ) as error:
        output(f"fetch-backfill manifest validation failed: {error}")
        output("Actor invocation: NO\nNo Apify API request made.")
        return 2

    supplemental_actor_id: str | None = None
    if include_all_successful_runs:
        try:
            supplemental_actor_id = load_seek_collection_config(
                actor_config_path
            ).actor_id
        except (SeekCollectionConfigurationError, OSError, ValueError) as error:
            output(f"fetch-backfill Actor configuration failed: {error}")
            output("Actor invocation: NO\nNo Apify API request made.")
            return 2

    if dry_run:
        output(
            render_backfill_fetch_dry_run(
                plan,
                include_all_successful_runs=include_all_successful_runs,
                supplemental_actor_id=supplemental_actor_id,
            )
        )
        return 0 if plan.source_manifest.is_ready else 2

    try:
        result = fetch_full_backfill(
            plan=plan,
            force=force,
            include_all_successful_runs=include_all_successful_runs,
            supplemental_actor_id=supplemental_actor_id,
            event_handler=output,
        )
    except (
        BackfillFetchError,
        ApifyCollectionError,
        CollectionConfigurationError,
        OSError,
        ValueError,
    ) as error:
        output(f"fetch-backfill failed safely: {error}")
        output("Actor invocation: NO")
        return 1

    output(render_backfill_fetch_summary(result))
    return 0 if result.manifest.status is BackfillFetchStatus.COMPLETE else 1
