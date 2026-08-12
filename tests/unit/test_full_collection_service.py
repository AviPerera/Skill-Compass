"""Test resumable sequential backfill orchestration with no real Apify calls."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from skill_compass.collection.full_backfill import ScopeDataset
from skill_compass.collection.models import CapStatus
from skill_compass.collection.search_scopes import (
    ClassificationDefinition,
    SearchScopeConfig,
    build_search_scopes,
)
from skill_compass.collection.seek_adapter import load_seek_collection_config
from skill_compass.services.full_collection import (
    BackfillStatus,
    FullCollectionPlan,
    FullCollectionSafetyError,
    ScopeStatus,
    build_full_collection_plan,
    execute_full_collection,
    render_forced_backfill_warning,
    run_full_collection_command,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACTOR_CONFIG_PATH = PROJECT_ROOT / "sources/apify_seek_current/collection.yaml"
SEARCH_CONFIG_PATH = PROJECT_ROOT / "profiles/data_analytics/search_scopes.yaml"
FIXED_TIME = datetime(2026, 8, 13, 4, 5, 6, tzinfo=UTC)


def _small_search_config() -> SearchScopeConfig:
    return SearchScopeConfig(
        profile_code="data_analytics",
        collection_strategy_version="test-1",
        keyword="Data Analyst",
        country="AU",
        country_name="Australia",
        cap_warning_threshold=500,
        fetch_descriptions=True,
        full_scope_max_items=0,
        locations={
            "NT": "Northern Territory NT",
            "QLD": "Queensland QLD",
        },
        simple_state_scopes=("NT", "QLD"),
        partitioned_states=(),
        classifications=(
            ClassificationDefinition(
                classification_id="1200", classification_name="Accounting"
            ),
        ),
    )


def _small_plan(output_root: Path) -> FullCollectionPlan:
    search_config = _small_search_config()
    actor_config = load_seek_collection_config(ACTOR_CONFIG_PATH)
    return FullCollectionPlan(
        search_config=search_config,
        actor_config=actor_config,
        scopes=build_search_scopes(search_config),
        output_root=output_root,
        previous_manifest=None,
        previous_manifest_path=None,
    )


class FakeSequentialClient:
    """Return configured raw items and reject concurrent scope starts."""

    def __init__(
        self,
        *,
        items_by_location: dict[str, tuple[dict[str, Any], ...]],
        failed_locations: set[str] | None = None,
        failure_message: str = "fictional Actor failure",
    ) -> None:
        self.items_by_location = items_by_location
        self.failed_locations = failed_locations or set()
        self.failure_message = failure_message
        self.execute_calls: list[dict[str, Any]] = []
        self.retrieve_calls: list[str] = []
        self.actor_resolved = False
        self.iterator_active = False

    def resolve_actor(self) -> None:
        self.actor_resolved = True

    def execute_scope(self, actor_input: dict[str, Any]) -> ScopeDataset:
        assert self.iterator_active is False, "scope execution must be sequential"
        self.execute_calls.append(dict(actor_input))
        location = actor_input["location"]
        if location in self.failed_locations:
            raise RuntimeError(self.failure_message)
        return self._dataset(location)

    def retrieve_existing_scope_dataset(
        self,
        *,
        run_id: str,
        dataset_id: str,
        started_at: datetime,
        finished_at: datetime | None,
    ) -> ScopeDataset:
        del run_id, started_at, finished_at
        self.retrieve_calls.append(dataset_id)
        location = dataset_id.removeprefix("dataset-")
        return self._dataset(location)

    def _dataset(self, location: str) -> ScopeDataset:
        items = self.items_by_location[location]

        def iterator():  # type: ignore[no-untyped-def]
            assert self.iterator_active is False
            self.iterator_active = True
            try:
                yield from items
            finally:
                self.iterator_active = False

        resource_code = "nt" if location.startswith("Northern") else "qld"
        return ScopeDataset(
            run_id=f"run-{resource_code}",
            dataset_id=f"dataset-{location}",
            status="SUCCEEDED",
            started_at=FIXED_TIME,
            finished_at=FIXED_TIME,
            items=iterator(),
        )


def _client_factory(client: FakeSequentialClient):  # type: ignore[no-untyped-def]
    return lambda _settings, _actor_id: client


def _default_items() -> dict[str, tuple[dict[str, Any], ...]]:
    return {
        "Northern Territory NT": ({"id": "job-a"}, {"id": "job-b"}),
        "Queensland QLD": (
            {"id": "job-b"},
            {"id": "job-c"},
            {"title": "missing stable identity"},
        ),
    }


def test_dry_run_and_missing_mode_make_zero_api_calls(tmp_path: Path) -> None:
    output: list[str] = []

    dry_exit = run_full_collection_command(
        dry_run=True,
        execute=False,
        resume=False,
        force=False,
        search_scopes_path=SEARCH_CONFIG_PATH,
        actor_config_path=ACTOR_CONFIG_PATH,
        output_root=tmp_path,
        output=output.append,
    )
    missing_mode_exit = run_full_collection_command(
        dry_run=False,
        execute=False,
        resume=False,
        force=False,
        output=output.append,
    )

    assert dry_exit == 0
    assert missing_mode_exit == 2
    assert "Total scopes expected:        66" in output[0]
    assert "No Actor requests made." in output[0]
    assert list(tmp_path.iterdir()) == []


def test_sequential_collection_consolidates_by_source_identity(tmp_path: Path) -> None:
    client = FakeSequentialClient(items_by_location=_default_items())

    result = execute_full_collection(
        plan=_small_plan(tmp_path),
        environ={"APIFY_TOKEN": "fictional-private-token"},
        clock=lambda: FIXED_TIME,
        client_factory=_client_factory(client),
    )

    manifest = result.manifest
    assert client.actor_resolved is True
    assert len(client.execute_calls) == 2
    assert manifest.status is BackfillStatus.COMPLETE
    assert manifest.expected_scope_count == 2
    assert manifest.successful_scope_count == 2
    assert manifest.failed_scope_count == 0
    assert manifest.raw_item_count == 5
    assert manifest.unique_source_job_count == 3
    assert manifest.cross_scope_duplicate_count == 1
    assert manifest.identity_failure_count == 1
    assert manifest.national_raw_path is not None
    national_items = [
        json.loads(line)
        for line in manifest.national_raw_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [item["id"] for item in national_items] == ["job-a", "job-b", "job-c"]
    assert manifest.provenance_path is not None
    assert len(manifest.provenance_path.read_text(encoding="utf-8").splitlines()) == 5


def test_scope_failure_preserves_success_and_resume_skips_it(tmp_path: Path) -> None:
    first_client = FakeSequentialClient(
        items_by_location=_default_items(), failed_locations={"Queensland QLD"}
    )
    first_result = execute_full_collection(
        plan=_small_plan(tmp_path),
        environ={"APIFY_TOKEN": "fictional-private-token"},
        clock=lambda: FIXED_TIME,
        client_factory=_client_factory(first_client),
    )

    assert first_result.manifest.status is BackfillStatus.PARTIAL
    assert first_result.manifest.successful_scope_count == 1
    assert first_result.manifest.failed_scope_count == 1
    nt_path = first_result.backfill_dir / "scopes/nt_state.jsonl"
    assert nt_path.exists()

    resume_plan = build_full_collection_plan(
        search_scopes_path=SEARCH_CONFIG_PATH,
        actor_config_path=ACTOR_CONFIG_PATH,
        output_root=tmp_path,
    )
    resume_plan = FullCollectionPlan(
        search_config=_small_search_config(),
        actor_config=resume_plan.actor_config,
        scopes=build_search_scopes(_small_search_config()),
        output_root=tmp_path,
        previous_manifest=resume_plan.previous_manifest,
        previous_manifest_path=resume_plan.previous_manifest_path,
    )
    events: list[str] = []
    resume_client = FakeSequentialClient(items_by_location=_default_items())
    resumed = execute_full_collection(
        plan=resume_plan,
        resume=True,
        environ={"APIFY_TOKEN": "fictional-private-token"},
        clock=lambda: FIXED_TIME,
        client_factory=_client_factory(resume_client),
        event_handler=events.append,
    )

    assert resumed.manifest.status is BackfillStatus.COMPLETE
    assert nt_path.exists()
    assert len(resume_client.execute_calls) == 1
    assert resume_client.execute_calls[0]["location"] == "Queensland QLD"
    assert "[SKIP] nt_state — completed" in events
    assert any(
        event.startswith("[RETRY] qld_state — previous failure") for event in events
    )


def test_cap_risk_at_and_above_threshold_does_not_stop_plan(tmp_path: Path) -> None:
    items = {
        "Northern Territory NT": tuple({"id": f"nt-{index}"} for index in range(500)),
        "Queensland QLD": tuple({"id": f"qld-{index}"} for index in range(501)),
    }
    client = FakeSequentialClient(items_by_location=items)

    result = execute_full_collection(
        plan=_small_plan(tmp_path),
        environ={"APIFY_TOKEN": "fictional-private-token"},
        clock=lambda: FIXED_TIME,
        client_factory=_client_factory(client),
    )

    assert [item.cap_status for item in result.scope_results] == [
        CapStatus.CAP_RISK,
        CapStatus.CAP_RISK,
    ]
    assert result.manifest.cap_risk_scope_count == 2
    assert result.manifest.status is BackfillStatus.COMPLETE
    assert len(client.execute_calls) == 2


def test_complete_backfill_is_protected_and_force_creates_new_directory(
    tmp_path: Path,
) -> None:
    first_client = FakeSequentialClient(items_by_location=_default_items())
    execute_full_collection(
        plan=_small_plan(tmp_path),
        environ={"APIFY_TOKEN": "fictional-private-token"},
        clock=lambda: FIXED_TIME,
        client_factory=_client_factory(first_client),
    )
    detected = build_full_collection_plan(
        search_scopes_path=SEARCH_CONFIG_PATH,
        actor_config_path=ACTOR_CONFIG_PATH,
        output_root=tmp_path,
    )
    protected_plan = FullCollectionPlan(
        search_config=_small_search_config(),
        actor_config=detected.actor_config,
        scopes=build_search_scopes(_small_search_config()),
        output_root=tmp_path,
        previous_manifest=detected.previous_manifest,
        previous_manifest_path=detected.previous_manifest_path,
    )
    client_created = False

    def forbidden_factory(_settings, _actor_id):  # type: ignore[no-untyped-def]
        nonlocal client_created
        client_created = True
        raise AssertionError("client must not be created")

    with pytest.raises(FullCollectionSafetyError):
        execute_full_collection(
            plan=protected_plan,
            environ={"APIFY_TOKEN": "fictional-private-token"},
            client_factory=forbidden_factory,
        )
    assert client_created is False

    force_client = FakeSequentialClient(items_by_location=_default_items())
    forced = execute_full_collection(
        plan=protected_plan,
        force=True,
        environ={"APIFY_TOKEN": "fictional-private-token"},
        clock=lambda: FIXED_TIME,
        client_factory=_client_factory(force_client),
    )
    assert forced.manifest.status is BackfillStatus.COMPLETE
    assert len(list(tmp_path.glob("*/collection_manifest.json"))) == 2
    assert len(force_client.execute_calls) == 2


def test_command_prints_existing_complete_details_before_no_action(
    tmp_path: Path,
) -> None:
    client = FakeSequentialClient(items_by_location=_default_items())
    completed = execute_full_collection(
        plan=_small_plan(tmp_path),
        environ={"APIFY_TOKEN": "fictional-private-token"},
        clock=lambda: FIXED_TIME,
        client_factory=_client_factory(client),
    )
    output: list[str] = []

    exit_code = run_full_collection_command(
        dry_run=False,
        execute=True,
        resume=False,
        force=False,
        search_scopes_path=SEARCH_CONFIG_PATH,
        actor_config_path=ACTOR_CONFIG_PATH,
        output_root=tmp_path,
        output=output.append,
    )

    warning = output[0]
    assert exit_code == 2
    assert "WARNING — FULL BACKFILL ALREADY EXISTS" in warning
    assert completed.manifest.backfill_id in warning
    assert "No API request has been made." in warning
    assert "FULL COLLECTION CANCELLED." in warning
    assert len(client.execute_calls) == 2


def test_force_warning_names_previous_backfill_and_new_scope_count(
    tmp_path: Path,
) -> None:
    client = FakeSequentialClient(items_by_location=_default_items())
    completed = execute_full_collection(
        plan=_small_plan(tmp_path),
        environ={"APIFY_TOKEN": "fictional-private-token"},
        clock=lambda: FIXED_TIME,
        client_factory=_client_factory(client),
    )

    warning = render_forced_backfill_warning(completed.manifest, planned_scope_count=66)

    assert "FORCED FULL BACKFILL" in warning
    assert completed.manifest.backfill_id in warning
    assert "New planned scopes: 66" in warning
    assert "may consume Apify credits" in warning


def test_failure_diagnostics_redact_token(tmp_path: Path) -> None:
    token = "fictional-secret-never-print"
    client = FakeSequentialClient(
        items_by_location=_default_items(),
        failed_locations={"Queensland QLD"},
        failure_message=f"remote failure included {token}",
    )

    events: list[str] = []
    result = execute_full_collection(
        plan=_small_plan(tmp_path),
        environ={"APIFY_TOKEN": token},
        clock=lambda: FIXED_TIME,
        client_factory=_client_factory(client),
        event_handler=events.append,
    )

    scope_csv = result.scope_results_path.read_text(encoding="utf-8")
    manifest_json = result.manifest_path.read_text(encoding="utf-8")
    assert token not in scope_csv
    assert token not in manifest_json
    assert token not in "\n".join(events)
    assert "[REDACTED]" in scope_csv
    failed = next(
        item for item in result.scope_results if item.status is ScopeStatus.FAILED
    )
    assert failed.error_message is not None
