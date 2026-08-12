"""Orchestrate the resumable one-time national Apify backfill.

This application service plans and sequentially coordinates paid scope runs,
private raw persistence, auditing, and consolidation. It must not clean, map,
extract, classify, analyze, or expose secrets.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from skill_compass.collection.apify_client import ApifyCollectionError
from skill_compass.collection.cap_assessment import assess_result_cap
from skill_compass.collection.full_backfill import (
    ApifyFullBackfillClient,
    ScopeDataset,
)
from skill_compass.collection.models import CapStatus
from skill_compass.collection.search_scopes import (
    DEFAULT_SEARCH_SCOPES_PATH,
    SearchScope,
    SearchScopeConfig,
    build_full_scope_actor_input,
    build_search_scopes,
    load_search_scope_config,
)
from skill_compass.collection.seek_adapter import (
    SeekCollectionConfig,
    find_source_job_id,
    load_seek_collection_config,
)
from skill_compass.config.settings import ApifySettings, load_apify_settings

# =============================================================================
# Public planning and persistence contracts
# =============================================================================


DEFAULT_ACTOR_CONFIG_PATH = Path("sources/apify_seek_current/collection.yaml")
DEFAULT_FULL_COLLECTION_ROOT = Path("data/private/collections/full")


class BackfillStatus(StrEnum):
    """Describe whether the configured national backfill is usable and complete."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ScopeStatus(StrEnum):
    """Describe one persisted scope outcome."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class FrozenModel(BaseModel):
    """Provide strict immutable behavior for persisted audit contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ScopeRunResult(FrozenModel):
    """Record one latest scope attempt without embedding private raw records."""

    scope_id: str
    state_code: str
    location: str
    classification_id: str | None = None
    classification_name: str | None = None
    status: ScopeStatus
    run_id: str | None = None
    dataset_id: str | None = None
    returned_item_count: int = Field(default=0, ge=0)
    unique_source_job_id_count: int = Field(default=0, ge=0)
    within_scope_duplicate_count: int = Field(default=0, ge=0)
    identity_failure_count: int = Field(default=0, ge=0)
    cap_status: CapStatus = CapStatus.UNKNOWN
    cap_reason: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    recorded_at: datetime
    attempt_count: int = Field(default=1, ge=1)
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_scope_result(self) -> ScopeRunResult:
        """Require aware audit times and reconciled successful-scope counts."""
        timestamps = (self.started_at, self.finished_at, self.recorded_at)
        if any(value is not None and value.tzinfo is None for value in timestamps):
            raise ValueError("scope result timestamps must be timezone-aware")
        if self.status is ScopeStatus.SUCCEEDED:
            if self.run_id is None or self.dataset_id is None:
                raise ValueError("successful scopes require run and dataset IDs")
            reconciled_count = (
                self.unique_source_job_id_count
                + self.within_scope_duplicate_count
                + self.identity_failure_count
            )
            if reconciled_count != self.returned_item_count:
                raise ValueError("successful scope identity counts must reconcile")
            if self.error_message is not None:
                raise ValueError("successful scopes must not contain an error")
        elif self.error_message is None:
            raise ValueError("failed scopes require a safe error message")
        return self


class CollectionManifest(FrozenModel):
    """Persist restart-safe national backfill status and aggregate evidence."""

    backfill_id: str
    profile_code: str
    source_code: str
    actor_id: str
    collection_strategy_version: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    status: BackfillStatus
    expected_scope_count: int = Field(ge=0)
    attempted_scope_count: int = Field(ge=0)
    successful_scope_count: int = Field(ge=0)
    failed_scope_count: int = Field(ge=0)
    raw_item_count: int = Field(ge=0)
    unique_source_job_count: int = Field(ge=0)
    cross_scope_duplicate_count: int = Field(ge=0)
    identity_failure_count: int = Field(ge=0)
    cap_risk_scope_count: int = Field(ge=0)
    successful_scope_ids: tuple[str, ...]
    failed_scope_ids: tuple[str, ...]
    national_raw_path: Path | None = None
    provenance_path: Path | None = None

    @model_validator(mode="after")
    def validate_manifest(self) -> CollectionManifest:
        """Require aware times and scope totals that cannot exceed the plan."""
        timestamps = (self.created_at, self.updated_at, self.completed_at)
        if any(value is not None and value.tzinfo is None for value in timestamps):
            raise ValueError("collection manifest timestamps must be timezone-aware")
        if self.attempted_scope_count > self.expected_scope_count:
            raise ValueError("attempted scopes cannot exceed expected scopes")
        if (
            self.successful_scope_count + self.failed_scope_count
            > self.attempted_scope_count
        ):
            raise ValueError("resolved scope counts cannot exceed attempted scopes")
        return self


@dataclass(frozen=True, slots=True)
class FullCollectionPlan:
    """Bundle validated source/profile configuration and derived ordered scopes."""

    search_config: SearchScopeConfig
    actor_config: SeekCollectionConfig
    scopes: tuple[SearchScope, ...]
    output_root: Path
    previous_manifest: CollectionManifest | None
    previous_manifest_path: Path | None


@dataclass(frozen=True, slots=True)
class FullCollectionResult:
    """Return final persisted audit evidence for an execution or resume."""

    manifest: CollectionManifest
    scope_results: tuple[ScopeRunResult, ...]
    backfill_dir: Path
    manifest_path: Path
    scope_results_path: Path


class FullCollectionSafetyError(RuntimeError):
    """Stop a paid operation before any Apify request is made."""

    def __init__(
        self,
        message: str,
        *,
        previous_manifest: CollectionManifest | None = None,
        previous_manifest_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.previous_manifest = previous_manifest
        self.previous_manifest_path = previous_manifest_path


class FullBackfillClient(Protocol):
    """Describe the sequential collection client required by orchestration."""

    def resolve_actor(self) -> None: ...

    def execute_scope(self, actor_input: Mapping[str, Any]) -> ScopeDataset: ...

    def retrieve_existing_scope_dataset(
        self,
        *,
        run_id: str,
        dataset_id: str,
        started_at: datetime,
        finished_at: datetime | None,
    ) -> ScopeDataset: ...


# =============================================================================
# Plan loading and previous-backfill discovery
# =============================================================================


def _read_manifest(path: Path) -> CollectionManifest:
    """Read one strict manifest, refusing to ignore corrupt safety state."""
    try:
        return CollectionManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise FullCollectionSafetyError(
            f"existing collection manifest could not be validated: {path}"
        ) from error


def find_latest_manifest(
    output_root: Path,
) -> tuple[CollectionManifest | None, Path | None]:
    """Find the latest persisted backfill manifest without changing any files."""
    if not output_root.exists():
        return None, None
    manifest_paths = tuple(output_root.glob("*/collection_manifest.json"))
    if not manifest_paths:
        return None, None
    latest_path = max(manifest_paths, key=lambda path: path.stat().st_mtime_ns)
    return _read_manifest(latest_path), latest_path


def build_full_collection_plan(
    *,
    search_scopes_path: Path = DEFAULT_SEARCH_SCOPES_PATH,
    actor_config_path: Path = DEFAULT_ACTOR_CONFIG_PATH,
    output_root: Path = DEFAULT_FULL_COLLECTION_ROOT,
) -> FullCollectionPlan:
    """Load both contracts, derive scopes, and inspect prior local backfills."""
    search_config = load_search_scope_config(search_scopes_path)
    actor_config = load_seek_collection_config(actor_config_path)
    scopes = build_search_scopes(search_config)
    previous_manifest, previous_path = find_latest_manifest(output_root)
    return FullCollectionPlan(
        search_config=search_config,
        actor_config=actor_config,
        scopes=scopes,
        output_root=output_root,
        previous_manifest=previous_manifest,
        previous_manifest_path=previous_path,
    )


# =============================================================================
# Atomic local audit persistence
# =============================================================================


_SCOPE_RESULT_FIELDS = tuple(ScopeRunResult.model_fields)


def _write_json_atomic(path: Path, content: str) -> None:
    """Replace one JSON audit file only after its full content is durable locally."""
    partial_path = path.with_suffix(path.suffix + ".partial")
    partial_path.write_text(content, encoding="utf-8")
    partial_path.replace(path)


def _write_manifest(path: Path, manifest: CollectionManifest) -> None:
    """Persist a validated manifest atomically."""
    _write_json_atomic(path, manifest.model_dump_json(indent=2) + "\n")


def _scope_result_csv_row(result: ScopeRunResult) -> dict[str, str | int]:
    """Serialize one typed scope result to stable scalar CSV values."""
    document = result.model_dump(mode="json")
    return {
        name: "" if document[name] is None else document[name]
        for name in _SCOPE_RESULT_FIELDS
    }


def _write_scope_results(
    path: Path,
    *,
    scopes: tuple[SearchScope, ...],
    results: Mapping[str, ScopeRunResult],
) -> None:
    """Rewrite the small ordered audit CSV atomically after each scope."""
    partial_path = path.with_suffix(path.suffix + ".partial")
    with partial_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=_SCOPE_RESULT_FIELDS)
        writer.writeheader()
        for scope in scopes:
            result = results.get(scope.scope_id)
            if result is not None:
                writer.writerow(_scope_result_csv_row(result))
    partial_path.replace(path)


def _load_scope_results(path: Path) -> dict[str, ScopeRunResult]:
    """Restore the latest result per scope for safe resume decisions."""
    if not path.exists():
        return {}
    results: dict[str, ScopeRunResult] = {}
    try:
        with path.open(encoding="utf-8", newline="") as input_file:
            for row in csv.DictReader(input_file):
                normalized = {
                    key: value if value != "" else None for key, value in row.items()
                }
                result = ScopeRunResult.model_validate(normalized)
                results[result.scope_id] = result
    except (OSError, csv.Error, ValidationError) as error:
        raise FullCollectionSafetyError(
            f"existing scope results could not be validated: {path}"
        ) from error
    return results


def _new_backfill_directory(output_root: Path, *, now: datetime) -> tuple[str, Path]:
    """Create a unique ignored backfill directory without overwriting prior work."""
    timestamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    base_id = f"full_{timestamp}"
    backfill_id = base_id
    backfill_dir = output_root / backfill_id
    suffix = 1
    while backfill_dir.exists():
        backfill_id = f"{base_id}_{suffix}"
        backfill_dir = output_root / backfill_id
        suffix += 1
    (backfill_dir / "scopes").mkdir(parents=True)
    return backfill_id, backfill_dir


# =============================================================================
# Per-scope raw persistence and audit calculation
# =============================================================================


def _persist_scope_dataset(
    *,
    scope: SearchScope,
    scope_dataset: ScopeDataset,
    scope_path: Path,
    source_job_id_paths: tuple[str, ...],
    cap_warning_threshold: int,
    attempt_count: int,
    recorded_at: datetime,
) -> ScopeRunResult:
    """Stream one successful dataset to JSONL and calculate its audit evidence."""
    partial_path = scope_path.with_suffix(scope_path.suffix + ".partial")
    returned_count = 0
    identity_failure_count = 0
    duplicate_count = 0
    seen_ids: set[str] = set()
    with partial_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for item in scope_dataset.items:
            output_file.write(
                json.dumps(item, ensure_ascii=False, separators=(",", ":"))
            )
            output_file.write("\n")
            returned_count += 1
            source_job_id = find_source_job_id(item, source_job_id_paths)
            if source_job_id is None:
                identity_failure_count += 1
            elif source_job_id in seen_ids:
                duplicate_count += 1
            else:
                seen_ids.add(source_job_id)
    partial_path.replace(scope_path)

    cap = assess_result_cap(
        returned_item_count=returned_count,
        warning_threshold=cap_warning_threshold,
    )
    return ScopeRunResult(
        scope_id=scope.scope_id,
        state_code=scope.state_code,
        location=scope.location,
        classification_id=scope.classification_id,
        classification_name=scope.classification_name,
        status=ScopeStatus.SUCCEEDED,
        run_id=scope_dataset.run_id,
        dataset_id=scope_dataset.dataset_id,
        returned_item_count=returned_count,
        unique_source_job_id_count=len(seen_ids),
        within_scope_duplicate_count=duplicate_count,
        identity_failure_count=identity_failure_count,
        cap_status=cap.status,
        cap_reason=cap.reason,
        started_at=scope_dataset.started_at,
        finished_at=scope_dataset.finished_at,
        recorded_at=recorded_at,
        attempt_count=attempt_count,
    )


def _failed_scope_result(
    *,
    scope: SearchScope,
    previous: ScopeRunResult | None,
    scope_dataset: ScopeDataset | None,
    error_message: str,
    recorded_at: datetime,
) -> ScopeRunResult:
    """Preserve known run/dataset IDs so resume can avoid another paid run."""
    return ScopeRunResult(
        scope_id=scope.scope_id,
        state_code=scope.state_code,
        location=scope.location,
        classification_id=scope.classification_id,
        classification_name=scope.classification_name,
        status=ScopeStatus.FAILED,
        run_id=(
            scope_dataset.run_id if scope_dataset else getattr(previous, "run_id", None)
        ),
        dataset_id=(
            scope_dataset.dataset_id
            if scope_dataset
            else getattr(previous, "dataset_id", None)
        ),
        cap_reason="Scope did not produce a complete retrievable dataset.",
        started_at=(
            scope_dataset.started_at
            if scope_dataset
            else getattr(previous, "started_at", None)
        ),
        finished_at=(
            scope_dataset.finished_at
            if scope_dataset
            else getattr(previous, "finished_at", None)
        ),
        recorded_at=recorded_at,
        attempt_count=(previous.attempt_count + 1 if previous else 1),
        error_message=error_message,
    )


# =============================================================================
# Deterministic national consolidation
# =============================================================================


@dataclass(frozen=True, slots=True)
class ConsolidationResult:
    """Return national raw and provenance reconciliation totals."""

    raw_item_count: int
    unique_source_job_count: int
    cross_scope_duplicate_count: int
    identity_failure_count: int
    national_raw_path: Path
    provenance_path: Path


def consolidate_successful_scopes(
    *,
    backfill_dir: Path,
    scopes: tuple[SearchScope, ...],
    results: Mapping[str, ScopeRunResult],
    source_code: str,
    source_job_id_paths: tuple[str, ...],
) -> ConsolidationResult:
    """Select first deterministic valid identity and retain occurrence provenance."""
    national_path = backfill_dir / "national_jobs_raw.jsonl"
    provenance_path = backfill_dir / "scope_provenance.jsonl"
    national_partial = national_path.with_suffix(national_path.suffix + ".partial")
    provenance_partial = provenance_path.with_suffix(
        provenance_path.suffix + ".partial"
    )

    raw_item_count = 0
    identity_failure_count = 0
    seen_identities: set[tuple[str, str]] = set()

    with (
        national_partial.open("w", encoding="utf-8", newline="\n") as national_file,
        provenance_partial.open("w", encoding="utf-8", newline="\n") as provenance_file,
    ):
        for scope in scopes:
            result = results.get(scope.scope_id)
            if result is None or result.status is not ScopeStatus.SUCCEEDED:
                continue
            scope_path = backfill_dir / "scopes" / f"{scope.scope_id}.jsonl"
            with scope_path.open(encoding="utf-8") as scope_file:
                for occurrence_number, line in enumerate(scope_file, start=1):
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        raise ValueError(
                            f"scope raw item is not a JSON object: {scope.scope_id}"
                        )
                    raw_item_count += 1
                    source_job_id = find_source_job_id(item, source_job_id_paths)
                    provenance = {
                        "source_code": source_code,
                        "source_job_id": source_job_id,
                        "scope_id": scope.scope_id,
                        "scope_occurrence_number": occurrence_number,
                        "identity_status": (
                            "VALID" if source_job_id is not None else "MISSING"
                        ),
                    }
                    provenance_file.write(
                        json.dumps(provenance, separators=(",", ":")) + "\n"
                    )
                    if source_job_id is None:
                        identity_failure_count += 1
                        continue
                    identity = (source_code, source_job_id)
                    if identity in seen_identities:
                        continue
                    seen_identities.add(identity)
                    national_file.write(line.rstrip("\r\n") + "\n")

    national_partial.replace(national_path)
    provenance_partial.replace(provenance_path)
    valid_occurrence_count = raw_item_count - identity_failure_count
    cross_scope_duplicate_count = valid_occurrence_count - len(seen_identities)
    return ConsolidationResult(
        raw_item_count=raw_item_count,
        unique_source_job_count=len(seen_identities),
        cross_scope_duplicate_count=cross_scope_duplicate_count,
        identity_failure_count=identity_failure_count,
        national_raw_path=national_path,
        provenance_path=provenance_path,
    )


# =============================================================================
# Manifest aggregation and paid sequential orchestration
# =============================================================================


def _aggregate_manifest(
    *,
    initial: CollectionManifest,
    scopes: tuple[SearchScope, ...],
    results: Mapping[str, ScopeRunResult],
    updated_at: datetime,
    final_status: BackfillStatus,
    consolidation: ConsolidationResult | None = None,
) -> CollectionManifest:
    """Recalculate every summary count from persisted latest scope results."""
    successful_ids = tuple(
        scope.scope_id
        for scope in scopes
        if results.get(scope.scope_id) is not None
        and results[scope.scope_id].status is ScopeStatus.SUCCEEDED
    )
    failed_ids = tuple(
        scope.scope_id
        for scope in scopes
        if results.get(scope.scope_id) is not None
        and results[scope.scope_id].status is ScopeStatus.FAILED
    )
    successful_results = [results[scope_id] for scope_id in successful_ids]
    raw_item_count = sum(result.returned_item_count for result in successful_results)
    identity_failure_count = sum(
        result.identity_failure_count for result in successful_results
    )
    cap_risk_count = sum(
        result.cap_status in {CapStatus.CAP_RISK, CapStatus.CONFIRMED_TRUNCATED}
        for result in successful_results
    )
    return initial.model_copy(
        update={
            "updated_at": updated_at,
            "completed_at": (
                updated_at
                if final_status
                in {
                    BackfillStatus.COMPLETE,
                    BackfillStatus.PARTIAL,
                    BackfillStatus.FAILED,
                }
                and len(results) == len(scopes)
                else None
            ),
            "status": final_status,
            "attempted_scope_count": len(results),
            "successful_scope_count": len(successful_ids),
            "failed_scope_count": len(failed_ids),
            "raw_item_count": (
                consolidation.raw_item_count if consolidation else raw_item_count
            ),
            "unique_source_job_count": (
                consolidation.unique_source_job_count if consolidation else 0
            ),
            "cross_scope_duplicate_count": (
                consolidation.cross_scope_duplicate_count if consolidation else 0
            ),
            "identity_failure_count": (
                consolidation.identity_failure_count
                if consolidation
                else identity_failure_count
            ),
            "cap_risk_scope_count": cap_risk_count,
            "successful_scope_ids": successful_ids,
            "failed_scope_ids": failed_ids,
            "national_raw_path": (
                consolidation.national_raw_path if consolidation else None
            ),
            "provenance_path": (
                consolidation.provenance_path if consolidation else None
            ),
        }
    )


def _safe_error_message(error: Exception, token: str) -> str:
    """Return bounded diagnostic text with any configured token removed."""
    message = f"{type(error).__name__}: {error}".replace(token, "[REDACTED]")
    return message[:500]


def _initial_manifest(
    *,
    backfill_id: str,
    plan: FullCollectionPlan,
    created_at: datetime,
) -> CollectionManifest:
    """Create the first restart-safe manifest before external API access."""
    return CollectionManifest(
        backfill_id=backfill_id,
        profile_code=plan.search_config.profile_code,
        source_code=plan.actor_config.source_code,
        actor_id=plan.actor_config.actor_id,
        collection_strategy_version=(plan.search_config.collection_strategy_version),
        created_at=created_at,
        updated_at=created_at,
        status=BackfillStatus.PARTIAL,
        expected_scope_count=len(plan.scopes),
        attempted_scope_count=0,
        successful_scope_count=0,
        failed_scope_count=0,
        raw_item_count=0,
        unique_source_job_count=0,
        cross_scope_duplicate_count=0,
        identity_failure_count=0,
        cap_risk_scope_count=0,
        successful_scope_ids=(),
        failed_scope_ids=(),
    )


def execute_full_collection(
    *,
    plan: FullCollectionPlan,
    resume: bool = False,
    force: bool = False,
    dotenv_path: Path = Path(".env"),
    environ: Mapping[str, str] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    client_factory: Callable[[ApifySettings, str], FullBackfillClient] = (
        lambda settings, actor_id: ApifyFullBackfillClient(
            settings=settings, actor_id=actor_id
        )
    ),
    event_handler: Callable[[str], None] = lambda _message: None,
) -> FullCollectionResult:
    """Run or resume every configured scope sequentially with immediate auditing."""
    if resume and force:
        raise FullCollectionSafetyError("--resume and --force cannot be combined")

    previous = plan.previous_manifest
    previous_path = plan.previous_manifest_path
    if resume:
        if previous is None or previous_path is None:
            raise FullCollectionSafetyError("no previous backfill exists to resume")
        if previous.status is BackfillStatus.COMPLETE:
            raise FullCollectionSafetyError(
                "completed backfills cannot be resumed",
                previous_manifest=previous,
                previous_manifest_path=previous_path,
            )
        if (
            previous.collection_strategy_version
            != plan.search_config.collection_strategy_version
            or previous.expected_scope_count != len(plan.scopes)
            or previous.actor_id != plan.actor_config.actor_id
            or previous.source_code != plan.actor_config.source_code
        ):
            raise FullCollectionSafetyError(
                "previous backfill configuration does not match the current plan",
                previous_manifest=previous,
                previous_manifest_path=previous_path,
            )
        backfill_dir = previous_path.parent
        backfill_id = previous.backfill_id
        initial_manifest = previous
    else:
        if previous is not None and not force:
            raise FullCollectionSafetyError(
                "a previous full backfill exists; use --resume for incomplete work "
                "or --force for a deliberate new historical collection",
                previous_manifest=previous,
                previous_manifest_path=previous_path,
            )
        created_at = clock()
        if created_at.tzinfo is None:
            raise ValueError("collection clock must return a timezone-aware datetime")
        backfill_id, backfill_dir = _new_backfill_directory(
            plan.output_root, now=created_at
        )
        initial_manifest = _initial_manifest(
            backfill_id=backfill_id,
            plan=plan,
            created_at=created_at,
        )

    manifest_path = backfill_dir / "collection_manifest.json"
    scope_results_path = backfill_dir / "scope_results.csv"
    results = _load_scope_results(scope_results_path) if resume else {}
    if resume and initial_manifest.successful_scope_count and not results:
        raise FullCollectionSafetyError(
            "resume audit is missing scope_results.csv; refusing to rerun paid scopes",
            previous_manifest=initial_manifest,
            previous_manifest_path=manifest_path,
        )
    if resume:
        missing_success_audits = set(initial_manifest.successful_scope_ids).difference(
            scope_id
            for scope_id, result in results.items()
            if result.status is ScopeStatus.SUCCEEDED
        )
        if missing_success_audits:
            raise FullCollectionSafetyError(
                "resume audit does not contain every previously successful scope",
                previous_manifest=initial_manifest,
                previous_manifest_path=manifest_path,
            )
    _write_manifest(manifest_path, initial_manifest)

    # Settings and client creation occur only after all local paid-run safeguards.
    settings = load_apify_settings(dotenv_path=dotenv_path, environ=environ)
    token = settings.token.get_secret_value()
    client = client_factory(settings, plan.actor_config.actor_id)
    try:
        client.resolve_actor()
    except Exception as error:
        failed_manifest = initial_manifest.model_copy(
            update={
                "updated_at": clock(),
                "completed_at": clock(),
                "status": BackfillStatus.FAILED,
            }
        )
        _write_manifest(manifest_path, failed_manifest)
        raise ApifyCollectionError(_safe_error_message(error, token)) from error

    total_scopes = len(plan.scopes)
    for index, scope in enumerate(plan.scopes, start=1):
        scope_path = backfill_dir / "scopes" / f"{scope.scope_id}.jsonl"
        previous_result = results.get(scope.scope_id)
        if (
            previous_result is not None
            and previous_result.status is ScopeStatus.SUCCEEDED
            and scope_path.exists()
        ):
            event_handler(f"[SKIP] {scope.scope_id} — completed")
            continue

        scope_dataset: ScopeDataset | None = None
        if previous_result is not None and previous_result.status is ScopeStatus.FAILED:
            event_handler(
                f"[RETRY] {scope.scope_id} — previous failure [{index:02d}/{total_scopes:02d}]"
            )
        elif previous_result is not None:
            event_handler(
                f"[RECOVER] {scope.scope_id} — raw file missing "
                f"[{index:02d}/{total_scopes:02d}]"
            )
        else:
            event_handler(f"[RUN {index:02d}/{total_scopes:02d}] {scope.scope_id}")
        event_handler(f"Location: {scope.location}")
        if scope.classification_id is not None:
            event_handler(
                f"Classification: {scope.classification_name} "
                f"({scope.classification_id})"
            )

        try:
            if (
                previous_result is not None
                and previous_result.run_id is not None
                and previous_result.dataset_id is not None
                and previous_result.started_at is not None
            ):
                scope_dataset = client.retrieve_existing_scope_dataset(
                    run_id=previous_result.run_id,
                    dataset_id=previous_result.dataset_id,
                    started_at=previous_result.started_at,
                    finished_at=previous_result.finished_at,
                )
            else:
                actor_input = build_full_scope_actor_input(
                    config=plan.search_config, scope=scope
                )
                scope_dataset = client.execute_scope(actor_input)

            result = _persist_scope_dataset(
                scope=scope,
                scope_dataset=scope_dataset,
                scope_path=scope_path,
                source_job_id_paths=plan.actor_config.source_job_id_paths,
                cap_warning_threshold=plan.search_config.cap_warning_threshold,
                attempt_count=(
                    previous_result.attempt_count + 1 if previous_result else 1
                ),
                recorded_at=clock(),
            )
            results[scope.scope_id] = result
            event_handler(
                "\n".join(
                    [
                        "Actor run: SUCCEEDED",
                        f"Items: {result.returned_item_count}",
                        f"Unique IDs: {result.unique_source_job_id_count}",
                        "Within-scope duplicates: "
                        f"{result.within_scope_duplicate_count}",
                        f"Identity failures: {result.identity_failure_count}",
                        f"Cap status: {result.cap_status.value}",
                    ]
                )
            )
        except Exception as error:
            failed_result = _failed_scope_result(
                scope=scope,
                previous=previous_result,
                scope_dataset=scope_dataset,
                error_message=_safe_error_message(error, token),
                recorded_at=clock(),
            )
            results[scope.scope_id] = failed_result
            event_handler(f"[FAILED] {scope.scope_id} — recorded; continuing")

        _write_scope_results(scope_results_path, scopes=plan.scopes, results=results)
        progress_manifest = _aggregate_manifest(
            initial=initial_manifest,
            scopes=plan.scopes,
            results=results,
            updated_at=clock(),
            final_status=BackfillStatus.PARTIAL,
        )
        _write_manifest(manifest_path, progress_manifest)

    successful_count = sum(
        result.status is ScopeStatus.SUCCEEDED for result in results.values()
    )
    consolidation: ConsolidationResult | None = None
    consolidation_error: Exception | None = None
    try:
        consolidation = consolidate_successful_scopes(
            backfill_dir=backfill_dir,
            scopes=plan.scopes,
            results=results,
            source_code=plan.actor_config.source_code,
            source_job_id_paths=plan.actor_config.source_job_id_paths,
        )
    except Exception as error:
        consolidation_error = error
        event_handler("[FAILED] national consolidation — backfill remains incomplete")

    all_succeeded = (
        len(results) == total_scopes
        and successful_count == total_scopes
        and consolidation is not None
    )
    if all_succeeded:
        final_status = BackfillStatus.COMPLETE
    elif successful_count:
        final_status = BackfillStatus.PARTIAL
    else:
        final_status = BackfillStatus.FAILED

    final_manifest = _aggregate_manifest(
        initial=initial_manifest,
        scopes=plan.scopes,
        results=results,
        updated_at=clock(),
        final_status=final_status,
        consolidation=consolidation,
    )
    _write_manifest(manifest_path, final_manifest)
    if consolidation_error is not None:
        event_handler(
            f"Consolidation error: {_safe_error_message(consolidation_error, token)}"
        )
    ordered_results = tuple(
        results[scope.scope_id] for scope in plan.scopes if scope.scope_id in results
    )
    return FullCollectionResult(
        manifest=final_manifest,
        scope_results=ordered_results,
        backfill_dir=backfill_dir,
        manifest_path=manifest_path,
        scope_results_path=scope_results_path,
    )


# =============================================================================
# Shared terminal reporting
# =============================================================================


def render_dry_run(plan: FullCollectionPlan) -> str:
    """Render the paid-operation plan without accessing Apify settings or clients."""
    config = plan.search_config
    simple_lines = "\n".join(
        config.locations[code] for code in config.simple_state_scopes
    )
    partition_lines = "\n".join(
        f"{config.locations[code]:34} {len(config.classifications)} classifications"
        for code in config.partitioned_states
    )
    per_partition = {
        code: sum(scope.state_code == code for scope in plan.scopes)
        for code in config.partitioned_states
    }
    partition_counts = "\n".join(
        f"{code} classification scopes:   {per_partition[code]}"
        for code in config.partitioned_states
    )
    return (
        "=" * 79
        + "\nSKILL COMPASS — FULL NATIONAL BACKFILL PLAN\n"
        + "=" * 79
        + f"\n\nSearch term: {config.keyword}\nCountry: {config.country_name}\n\n"
        + "STATE-LEVEL COLLECTION\n"
        + "-" * 79
        + f"\n{simple_lines}\n\nState-level scopes:            "
        + f"{len(config.simple_state_scopes)}\n\nCLASSIFICATION COLLECTION\n"
        + "-" * 79
        + f"\n{partition_lines}\n\n{partition_counts}\n\n"
        + "-" * 79
        + f"\nTotal scopes expected:        {config.expected_scope_count}"
        + f"\nActor runs planned:           {len(plan.scopes)}"
        + f"\nResult-cap warning:           {config.cap_warning_threshold}"
        + "\n\nDRY RUN ONLY\n\nNo Actor requests made."
        + "\nNo Apify credits consumed.\n"
    )


def render_previous_backfill_warning(
    manifest: CollectionManifest, *, resume_command: str
) -> str:
    """Render prior COMPLETE/PARTIAL/FAILED details before paid-run decisions."""
    heading = (
        "WARNING — FULL BACKFILL ALREADY EXISTS"
        if manifest.status is BackfillStatus.COMPLETE
        else (
            "PARTIAL BACKFILL FOUND"
            if manifest.status is BackfillStatus.PARTIAL
            else "FAILED BACKFILL FOUND"
        )
    )
    lines = [
        "=" * 79,
        heading,
        "=" * 79,
        "",
        f"Previous backfill ID:    {manifest.backfill_id}",
        f"Status:                  {manifest.status.value}",
        f"Completed at:            {manifest.completed_at or 'Not complete'}",
        f"Total scopes:            {manifest.expected_scope_count}",
        f"Successful scopes:       {manifest.successful_scope_count}",
        f"Failed/missing scopes:   {manifest.expected_scope_count - manifest.successful_scope_count}",
        f"Unique SEEK jobs:        {manifest.unique_source_job_count}",
        f"Raw items:              {manifest.raw_item_count}",
        f"Cap-risk scopes:        {manifest.cap_risk_scope_count}",
        "",
    ]
    if manifest.status is BackfillStatus.COMPLETE:
        lines.extend(
            [
                "Running the full collection again may repeat approximately "
                f"{manifest.expected_scope_count} paid Apify Actor runs.",
                "",
                "No API request has been made.",
                "Recommended actions:",
                "- use the existing national_jobs_raw.jsonl for processing;",
                "- use fetch-apify to recover an existing Apify dataset;",
                "- use the future collect-daily command once implemented;",
                "- use --force only for an intentional new historical collection.",
                "",
                "FULL COLLECTION CANCELLED.",
            ]
        )
    else:
        lines.extend(
            [
                "Recommended action: resume the existing backfill.",
                "Successful scopes will not be rerun.",
                "",
                resume_command,
                "",
                "No API request has been made.",
            ]
        )
    return "\n".join(lines) + "\n"


def render_forced_backfill_warning(
    manifest: CollectionManifest, *, planned_scope_count: int
) -> str:
    """Render explicit paid-operation warning when --force overrides protection."""
    return (
        "=" * 79
        + "\nFORCED FULL BACKFILL\n"
        + "=" * 79
        + "\n\nA previous backfill exists.\n"
        + "\nYou explicitly requested a new full collection."
        + f"\n\nPrevious backfill: {manifest.backfill_id}"
        + f"\nPrevious status:   {manifest.status.value}"
        + f"\nNew planned scopes: {planned_scope_count}"
        + "\n\nThis operation may consume Apify credits.\n"
    )


def render_full_collection_summary(result: FullCollectionResult) -> str:
    """Render final counts and every real cap-risk scope."""
    manifest = result.manifest
    cap_results = [
        scope_result
        for scope_result in result.scope_results
        if scope_result.cap_status
        in {CapStatus.CAP_RISK, CapStatus.CONFIRMED_TRUNCATED}
    ]
    cap_lines = ["CAP-RISK SCOPES", "-" * 79]
    if cap_results:
        cap_lines.append(f"{'Scope':44} {'Items':>8}    Status")
        cap_lines.extend(
            f"{item.scope_id:44} {item.returned_item_count:>8}    {item.cap_status.value}"
            for item in cap_results
        )
    else:
        cap_lines.append("None.")
    cap_lines.extend(
        [
            "",
            f"{len(cap_results)} scopes require further review or partitioning.",
            "",
        ]
    )

    summary_lines = [
        "=" * 79,
        "FULL NATIONAL COLLECTION SUMMARY",
        "=" * 79,
        "",
        f"Total scopes expected:       {manifest.expected_scope_count}",
        f"Scopes attempted:            {manifest.attempted_scope_count}",
        f"Successful:                  {manifest.successful_scope_count}",
        f"Failed:                      {manifest.failed_scope_count}",
        "",
        f"Raw items fetched:           {manifest.raw_item_count}",
        f"Unique SEEK jobs:            {manifest.unique_source_job_count}",
        f"Cross-scope duplicates:      {manifest.cross_scope_duplicate_count}",
        f"Identity failures:           {manifest.identity_failure_count}",
        "",
        f"Cap-risk scopes:             {manifest.cap_risk_scope_count}",
        "",
        f"Backfill status:             {manifest.status.value}",
        "",
        "National raw file:",
        str(manifest.national_raw_path or "Not created"),
        "",
    ]
    return "\n".join([*cap_lines, *summary_lines])


def run_full_collection_command(
    *,
    dry_run: bool,
    execute: bool,
    resume: bool,
    force: bool,
    search_scopes_path: Path = DEFAULT_SEARCH_SCOPES_PATH,
    actor_config_path: Path = DEFAULT_ACTOR_CONFIG_PATH,
    output_root: Path = DEFAULT_FULL_COLLECTION_ROOT,
    output: Callable[[str], None] = print,
    resume_command: str = (
        "uv run python scripts/run_full_collection.py --execute --resume"
    ),
) -> int:
    """Share the thin script/CLI mode handling and paid-run safety reporting."""
    if dry_run == execute:
        output("Choose exactly one of --dry-run or --execute. No API request made.")
        return 2
    if dry_run and (resume or force):
        output("--resume and --force apply only to --execute. No API request made.")
        return 2
    if resume and force:
        output("--resume and --force cannot be combined. No API request made.")
        return 2

    try:
        plan = build_full_collection_plan(
            search_scopes_path=search_scopes_path,
            actor_config_path=actor_config_path,
            output_root=output_root,
        )
    except Exception as error:
        output(f"collect-full configuration failed: {error}")
        return 1

    if dry_run:
        output(render_dry_run(plan))
        return 0

    previous = plan.previous_manifest
    if previous is not None:
        if force:
            output(
                render_forced_backfill_warning(
                    previous, planned_scope_count=len(plan.scopes)
                )
            )
        elif resume and previous.status is not BackfillStatus.COMPLETE:
            output(
                render_previous_backfill_warning(
                    previous, resume_command=resume_command
                )
            )
            output("RESUMING EXISTING BACKFILL\n")
        else:
            output(
                render_previous_backfill_warning(
                    previous, resume_command=resume_command
                )
            )
            return 2
    elif resume:
        output("No previous backfill exists to resume. No API request made.")
        return 2

    try:
        result = execute_full_collection(
            plan=plan,
            resume=resume,
            force=force,
            event_handler=output,
        )
    except FullCollectionSafetyError as error:
        output(f"FULL COLLECTION CANCELLED: {error}\nNo API request has been made.")
        return 2
    except Exception as error:
        output(f"collect-full failed safely: {error}")
        return 1

    output(render_full_collection_summary(result))
    return 0 if result.manifest.status is BackfillStatus.COMPLETE else 1
