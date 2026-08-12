"""Test occurrence-preserving batch retrieval with fake existing Apify storage."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from skill_compass.collection.backfill_sources import load_backfill_source_manifest
from skill_compass.collection.models import CapStatus
from skill_compass.collection.search_scopes import (
    ClassificationDefinition,
    SearchScopeConfig,
    build_search_scopes,
    load_search_scope_config,
)
from skill_compass.services.demo_feature_4 import (
    Feature4DemoResult,
    render_feature_4_demo,
)
from skill_compass.services.fetch_backfill import (
    BackfillFetchPlan,
    BackfillFetchStatus,
    ScopeFetchStatus,
    build_backfill_fetch_plan,
    build_successful_run_fetch_plan,
    fetch_full_backfill,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEARCH_SCOPES_PATH = PROJECT_ROOT / "profiles/data_analytics/search_scopes.yaml"
FIXED_TIME = datetime(2026, 8, 13, 5, 6, 7, tzinfo=UTC)


def _discovered_run(run_id: str, dataset_id: str, *, minute: int) -> SimpleNamespace:
    """Build minimal successful-run metadata returned by the SDK iterator."""
    return SimpleNamespace(
        id=run_id,
        default_dataset_id=dataset_id,
        default_key_value_store_id=f"store-{run_id}",
        started_at=datetime(2026, 8, 1, 1, minute, tzinfo=UTC),
    )


class FakeDatasetClient:
    """Expose all logical pages through the existing dataset iterator."""

    def __init__(
        self,
        *,
        pages: tuple[tuple[dict[str, Any], ...], ...],
        exists: bool = True,
        run_id: str | None = None,
    ) -> None:
        self.pages = pages
        self.exists = exists
        self.run_id = run_id
        self.iteration_count = 0

    def get(self):  # type: ignore[no-untyped-def]
        if not self.exists:
            return None
        return SimpleNamespace(act_run_id=self.run_id, act_id="existing-actor")

    def iterate_items(self):  # type: ignore[no-untyped-def]
        self.iteration_count += 1
        for page in self.pages:
            yield from page


class FakeRunClient:
    """Resolve only pre-existing run metadata."""

    def __init__(self, run: SimpleNamespace | None) -> None:
        self.existing_run = run
        self.get_count = 0

    def get(self):  # type: ignore[no-untyped-def]
        self.get_count += 1
        return self.existing_run


class FakeRunCollection:
    """Expose paginated successful-run discovery without mutation methods."""

    def __init__(self, pages: tuple[tuple[SimpleNamespace, ...], ...]) -> None:
        self.pages = pages
        self.iterate_calls: list[dict[str, Any]] = []

    def iterate(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        self.iterate_calls.append(kwargs)
        for page in self.pages:
            yield from page


class ReadOnlyActorClient:
    """Permit run listing while forbidding every paid Actor invocation path."""

    def __init__(self, run_collection: FakeRunCollection) -> None:
        self.run_collection = run_collection

    def runs(self) -> FakeRunCollection:
        return self.run_collection

    def call(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Feature 4B must never call an Actor")

    def start(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Feature 4B must never start an Actor")


class FakeKeyValueStoreClient:
    """Return one read-only Actor input record for provenance reporting."""

    def __init__(self, value: dict[str, Any] | None) -> None:
        self.value = value

    def get_record(self, key: str) -> dict[str, Any] | None:
        assert key == "INPUT"
        return None if self.value is None else {"key": key, "value": self.value}


class NoActorApifyClient:
    """Fail the test if batch retrieval touches any Actor interface."""

    def __init__(
        self,
        token: str,
        *,
        datasets: dict[str, FakeDatasetClient],
        runs: dict[str, SimpleNamespace | None] | None = None,
        discovered_run_pages: tuple[tuple[SimpleNamespace, ...], ...] = (),
        run_inputs: dict[str, dict[str, Any] | None] | None = None,
    ) -> None:
        self.token = token
        self.datasets = datasets
        self.runs = runs or {}
        self.dataset_requests: list[str] = []
        self.run_requests: list[str] = []
        self.actor_requests: list[str] = []
        self.run_collection = FakeRunCollection(discovered_run_pages)
        self.run_inputs = run_inputs or {}

    def actor(self, actor_id: str) -> ReadOnlyActorClient:
        self.actor_requests.append(actor_id)
        return ReadOnlyActorClient(self.run_collection)

    def dataset(self, dataset_id: str) -> FakeDatasetClient:
        self.dataset_requests.append(dataset_id)
        return self.datasets.get(
            dataset_id,
            FakeDatasetClient(pages=(), exists=False),
        )

    def run(self, run_id: str) -> FakeRunClient:
        self.run_requests.append(run_id)
        return FakeRunClient(self.runs.get(run_id))

    def key_value_store(self, store_id: str) -> FakeKeyValueStoreClient:
        return FakeKeyValueStoreClient(self.run_inputs.get(store_id))


def _small_config() -> SearchScopeConfig:
    return SearchScopeConfig(
        profile_code="data_analytics",
        collection_strategy_version="test-1",
        keyword="Data Analyst",
        country="AU",
        country_name="Australia",
        cap_warning_threshold=500,
        fetch_descriptions=True,
        full_scope_max_items=0,
        locations={"NT": "Northern Territory NT", "QLD": "Queensland QLD"},
        simple_state_scopes=("NT", "QLD"),
        partitioned_states=(),
        classifications=(
            ClassificationDefinition(
                classification_id="1200", classification_name="Accounting"
            ),
        ),
    )


def _small_plan(tmp_path: Path, manifest_rows: str) -> BackfillFetchPlan:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source_path = tmp_path / "sources.csv"
    source_path.write_text(
        "scope_id,run_id,dataset_id\n" + manifest_rows,
        encoding="utf-8",
    )
    config = _small_config()
    scopes = build_search_scopes(config)
    return BackfillFetchPlan(
        search_config=config,
        scopes=scopes,
        source_manifest=load_backfill_source_manifest(
            source_path, configured_scopes=scopes
        ),
        output_root=tmp_path / "output",
        backfill_id="test_backfill",
    )


def _run(
    *,
    plan: BackfillFetchPlan,
    client: NoActorApifyClient,
    force: bool = False,
    include_all_successful_runs: bool = False,
    events: list[str] | None = None,
):  # type: ignore[no-untyped-def]
    return fetch_full_backfill(
        plan=plan,
        force=force,
        include_all_successful_runs=include_all_successful_runs,
        supplemental_actor_id=(
            "scrapersdelight/seek-jobs-scraper" if include_all_successful_runs else None
        ),
        environ={"APIFY_TOKEN": "fictional-private-token"},
        client_factory=lambda _token: client,
        clock=lambda: FIXED_TIME,
        event_handler=(events if events is not None else []).append,
    )


def test_multiple_paginated_datasets_preserve_duplicate_rows_and_order(
    tmp_path: Path,
) -> None:
    plan = _small_plan(
        tmp_path,
        "qld_state,run-qld,\nnt_state,,dataset-nt\n",
    )
    datasets = {
        "dataset-nt": FakeDatasetClient(
            pages=(({"id": "duplicate-job", "scope": "nt"},),)
        ),
        "dataset-qld": FakeDatasetClient(
            pages=(
                ({"id": "duplicate-job", "scope": "qld-first"},),
                ({"id": "qld-only", "scope": "qld-second"},),
            )
        ),
    }
    client = NoActorApifyClient(
        "fictional-private-token",
        datasets=datasets,
        runs={
            "run-qld": SimpleNamespace(
                default_dataset_id="dataset-qld", act_id="existing-actor"
            )
        },
    )

    result = _run(plan=plan, client=client)

    combined = [
        json.loads(line)
        for line in result.national_raw_path.read_text(encoding="utf-8").splitlines()
    ]
    assert combined == [
        {"id": "duplicate-job", "scope": "nt"},
        {"id": "duplicate-job", "scope": "qld-first"},
        {"id": "qld-only", "scope": "qld-second"},
    ]
    assert [item["id"] for item in combined].count("duplicate-job") == 2
    assert result.manifest.raw_listing_count == 3
    assert result.manifest.combined_jsonl_row_count == 3
    assert result.manifest.reconciliation_status == "PASS"
    assert result.manifest.status is BackfillFetchStatus.COMPLETE
    assert result.manifest.duplicate_removal == "DEFERRED_TO_FEATURE_2"
    assert client.run_requests == ["run-qld"]
    assert client.dataset_requests == ["dataset-nt", "dataset-qld"]

    first_output = result.national_raw_path.read_bytes()
    repeated = _run(
        plan=plan,
        client=NoActorApifyClient(
            "fictional-private-token",
            datasets=datasets,
            runs={
                "run-qld": SimpleNamespace(
                    default_dataset_id="dataset-qld", act_id="existing-actor"
                )
            },
        ),
        force=True,
    )
    assert repeated.national_raw_path.read_bytes() == first_output


def test_empty_failed_and_missing_scopes_produce_partial_or_failed_status(
    tmp_path: Path,
) -> None:
    partial_plan = _small_plan(
        tmp_path, "nt_state,,dataset-empty\nqld_state,,missing\n"
    )
    partial_client = NoActorApifyClient(
        "fictional-private-token",
        datasets={
            "dataset-empty": FakeDatasetClient(pages=()),
            "missing": FakeDatasetClient(pages=(), exists=False),
        },
    )

    partial = _run(plan=partial_plan, client=partial_client)

    assert partial.manifest.status is BackfillFetchStatus.PARTIAL
    assert partial.manifest.successful_scope_count == 1
    assert partial.manifest.failed_scope_count == 1
    assert partial.manifest.raw_listing_count == 0
    assert partial.national_raw_path.read_bytes() == b""

    missing_plan = _small_plan(tmp_path / "missing_scope", "nt_state,,dataset-nt\n")
    missing_client = NoActorApifyClient(
        "fictional-private-token",
        datasets={"dataset-nt": FakeDatasetClient(pages=(({"id": "nt"},),))},
    )
    missing = _run(plan=missing_plan, client=missing_client)
    assert missing.manifest.status is BackfillFetchStatus.PARTIAL
    assert missing.manifest.successful_scope_count == 1
    assert missing.manifest.missing_scope_count == 1

    failed_plan = _small_plan(tmp_path / "failed", "nt_state,,missing\n")
    failed_client = NoActorApifyClient(
        "fictional-private-token",
        datasets={"missing": FakeDatasetClient(pages=(), exists=False)},
    )
    failed = _run(plan=failed_plan, client=failed_client)
    assert failed.manifest.status is BackfillFetchStatus.FAILED
    assert failed.manifest.missing_scope_count == 1
    assert failed.manifest.successful_scope_count == 0


def test_successful_run_discovery_adds_only_unrepresented_datasets(
    tmp_path: Path,
) -> None:
    plan = _small_plan(
        tmp_path,
        "nt_state,,dataset-nt\nqld_state,run-qld,\n",
    )
    discovered_pages = (
        (
            _discovered_run("run-nt", "dataset-nt", minute=1),
            _discovered_run("run-qld", "dataset-qld", minute=2),
            _discovered_run("run-extra-a", "dataset-extra-a", minute=3),
        ),
        (
            _discovered_run("run-extra-duplicate", "dataset-extra-a", minute=4),
            _discovered_run("run-extra-b", "dataset-extra-b", minute=5),
        ),
    )
    datasets = {
        "dataset-nt": FakeDatasetClient(pages=(({"id": "repeated", "origin": "nt"},),)),
        "dataset-qld": FakeDatasetClient(pages=(({"id": "qld", "origin": "qld"},),)),
        "dataset-extra-a": FakeDatasetClient(
            pages=(({"id": "repeated", "origin": "extra-a"},),)
        ),
        "dataset-extra-b": FakeDatasetClient(
            pages=(
                ({"id": "extra-b-1", "origin": "extra-b"},),
                ({"id": "extra-b-2", "origin": "extra-b"},),
            )
        ),
    }
    client = NoActorApifyClient(
        "fictional-private-token",
        datasets=datasets,
        runs={
            "run-qld": SimpleNamespace(
                default_dataset_id="dataset-qld", act_id="existing-actor"
            )
        },
        discovered_run_pages=discovered_pages,
        run_inputs={
            "store-run-nt": {"location": "Northern Territory NT"},
            "store-run-qld": {"location": "Queensland QLD"},
            "store-run-extra-a": {
                "location": "Queensland QLD",
                "classification": "1200",
            },
            "store-run-extra-duplicate": {
                "location": "Queensland QLD",
                "classification": "1200",
            },
            "store-run-extra-b": {"location": "Northern Territory NT"},
        },
    )

    result = _run(
        plan=plan,
        client=client,
        include_all_successful_runs=True,
    )

    combined = [
        json.loads(line)
        for line in result.national_raw_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [item["origin"] for item in combined] == [
        "nt",
        "qld",
        "extra-a",
        "extra-b",
        "extra-b",
    ]
    assert [item["id"] for item in combined].count("repeated") == 2
    assert result.manifest.discovered_successful_run_count == 5
    assert result.manifest.excluded_discovered_run_count == 3
    assert result.manifest.supplemental_dataset_count == 2
    assert result.manifest.successful_supplemental_count == 2
    assert result.manifest.supplemental_raw_listing_count == 3
    assert result.manifest.raw_listing_count == 5
    assert result.manifest.status is BackfillFetchStatus.COMPLETE
    assert [item.run_id for item in result.supplemental_results] == [
        "run-extra-a",
        "run-extra-b",
    ]
    assert client.actor_requests == ["scrapersdelight/seek-jobs-scraper"]
    assert client.run_collection.iterate_calls == [
        {"status": "SUCCEEDED", "desc": False}
    ]
    assert result.supplemental_results_path is not None
    assert result.supplemental_results_path.exists()
    assert result.supplemental_results[0].state_code == "QLD"
    assert result.supplemental_results[0].classification_name == "Accounting"
    assert result.supplemental_results[0].scope_type == "classification"
    assert result.supplemental_results[1].state_code == "NT"
    assert result.supplemental_results[1].scope_type == "state"

    demonstration = render_feature_4_demo(
        Feature4DemoResult(
            fetch=result,
            search_config=plan.search_config,
            actor_id="scrapersdelight/seek-jobs-scraper",
        )
    )
    assert "API authentication:           SUCCESS" in demonstration
    assert "Raw listings retrieved:       5" in demonstration
    assert "Queensland QLD" in demonstration
    assert "Northern Territory NT" in demonstration
    assert "Duplicates have NOT been removed." in demonstration
    assert "Overall result:               PASS" in demonstration

    resumed_client = NoActorApifyClient(
        "fictional-private-token",
        datasets=datasets,
        discovered_run_pages=discovered_pages,
    )
    resumed = _run(
        plan=plan,
        client=resumed_client,
        include_all_successful_runs=True,
    )
    assert resumed.manifest.status is BackfillFetchStatus.COMPLETE
    assert resumed_client.dataset_requests == []


def test_discovery_only_fetch_has_no_configured_missing_scopes_and_completes(
    tmp_path: Path,
) -> None:
    plan = build_successful_run_fetch_plan(
        search_scopes_path=SEARCH_SCOPES_PATH,
        output_root=tmp_path / "output",
    )
    client = NoActorApifyClient(
        "fictional-private-token",
        datasets={
            "dataset-one": FakeDatasetClient(pages=(({"id": "one"},),)),
            "dataset-two": FakeDatasetClient(pages=(({"id": "two"},),)),
        },
        discovered_run_pages=(
            (
                _discovered_run("run-one", "dataset-one", minute=1),
                _discovered_run("run-two", "dataset-two", minute=2),
            ),
        ),
    )
    events: list[str] = []

    result = _run(
        plan=plan,
        client=client,
        include_all_successful_runs=True,
        events=events,
    )

    assert plan.scopes == ()
    assert result.manifest.expected_scope_count == 0
    assert result.manifest.missing_scope_count == 0
    assert result.manifest.successful_supplemental_count == 2
    assert result.manifest.status is BackfillFetchStatus.COMPLETE
    assert all("[MISSING]" not in event for event in events)
    assert result.national_raw_path.read_text(encoding="utf-8").count("\n") == 2


def test_supplemental_failure_is_partial_and_later_datasets_are_preserved(
    tmp_path: Path,
) -> None:
    plan = _small_plan(
        tmp_path,
        "nt_state,,dataset-nt\nqld_state,,dataset-qld\n",
    )
    client = NoActorApifyClient(
        "fictional-private-token",
        datasets={
            "dataset-nt": FakeDatasetClient(pages=(({"id": "nt"},),)),
            "dataset-qld": FakeDatasetClient(pages=(({"id": "qld"},),)),
            "missing-extra": FakeDatasetClient(pages=(), exists=False),
            "working-extra": FakeDatasetClient(pages=(({"id": "extra"},),)),
        },
        discovered_run_pages=(
            (
                _discovered_run("run-failed", "missing-extra", minute=1),
                _discovered_run("run-working", "working-extra", minute=2),
            ),
        ),
    )

    result = _run(
        plan=plan,
        client=client,
        include_all_successful_runs=True,
    )

    assert result.manifest.status is BackfillFetchStatus.PARTIAL
    assert result.manifest.failed_supplemental_count == 1
    assert result.manifest.successful_supplemental_count == 1
    assert result.manifest.raw_listing_count == 3
    assert result.national_raw_path.read_text(encoding="utf-8").count("\n") == 3


def test_discovery_failure_preserves_configured_data_and_redacts_token(
    tmp_path: Path,
) -> None:
    token = "fictional-private-token"
    plan = _small_plan(
        tmp_path,
        "nt_state,,dataset-nt\nqld_state,,dataset-qld\n",
    )

    configured_datasets = {
        "dataset-nt": FakeDatasetClient(pages=(({"id": "nt"},),)),
        "dataset-qld": FakeDatasetClient(pages=(({"id": "qld"},),)),
        "dataset-extra": FakeDatasetClient(pages=(({"id": "extra"},),)),
    }
    first_client = NoActorApifyClient(
        token,
        datasets=configured_datasets,
        discovered_run_pages=(
            (_discovered_run("run-extra", "dataset-extra", minute=1),),
        ),
    )
    first = _run(
        plan=plan,
        client=first_client,
        include_all_successful_runs=True,
    )
    assert first.manifest.raw_listing_count == 3

    class BrokenDiscoveryClient(NoActorApifyClient):
        def actor(self, actor_id: str) -> ReadOnlyActorClient:
            self.actor_requests.append(actor_id)
            raise RuntimeError(f"discovery denied for {token}")

    client = BrokenDiscoveryClient(
        token,
        datasets={},
    )

    result = _run(
        plan=plan,
        client=client,
        include_all_successful_runs=True,
    )

    assert result.manifest.status is BackfillFetchStatus.PARTIAL
    assert result.manifest.supplemental_discovery_status.value == "FAILED"
    assert result.manifest.raw_listing_count == 3
    assert result.manifest.successful_supplemental_count == 1
    assert token not in result.manifest_path.read_text(encoding="utf-8")


def test_resume_skips_success_retries_failure_and_force_refetches(
    tmp_path: Path,
) -> None:
    plan = _small_plan(
        tmp_path,
        "nt_state,,dataset-nt\nqld_state,,dataset-qld\n",
    )
    first_client = NoActorApifyClient(
        "fictional-private-token",
        datasets={
            "dataset-nt": FakeDatasetClient(pages=(({"id": "nt"},),)),
            "dataset-qld": FakeDatasetClient(pages=(), exists=False),
        },
    )
    _run(plan=plan, client=first_client)

    events: list[str] = []
    resumed_client = NoActorApifyClient(
        "fictional-private-token",
        datasets={
            "dataset-nt": FakeDatasetClient(pages=(({"id": "nt-new"},),)),
            "dataset-qld": FakeDatasetClient(pages=(({"id": "qld"},),)),
        },
    )
    resumed = _run(plan=plan, client=resumed_client, events=events)

    assert resumed.manifest.status is BackfillFetchStatus.COMPLETE
    assert resumed_client.dataset_requests == ["dataset-qld"]
    assert "[SKIP] nt_state — already fetched" in events
    assert "[RETRY] qld_state — previous fetch failed" in events

    forced_client = NoActorApifyClient(
        "fictional-private-token",
        datasets={
            "dataset-nt": FakeDatasetClient(pages=(({"id": "nt-forced"},),)),
            "dataset-qld": FakeDatasetClient(pages=(({"id": "qld-forced"},),)),
        },
    )
    forced = _run(plan=plan, client=forced_client, force=True)
    assert forced_client.dataset_requests == ["dataset-nt", "dataset-qld"]
    forced_items = [
        json.loads(line)
        for line in forced.national_raw_path.read_text(encoding="utf-8").splitlines()
    ]
    assert forced_items == [{"id": "nt-forced"}, {"id": "qld-forced"}]


def test_cap_risk_at_500_and_501_and_zero_cap_risk(tmp_path: Path) -> None:
    plan = _small_plan(
        tmp_path,
        "nt_state,,dataset-499\nqld_state,,dataset-500\n",
    )
    client = NoActorApifyClient(
        "fictional-private-token",
        datasets={
            "dataset-499": FakeDatasetClient(
                pages=(tuple({"id": f"a-{index}"} for index in range(499)),)
            ),
            "dataset-500": FakeDatasetClient(
                pages=(tuple({"id": f"b-{index}"} for index in range(500)),)
            ),
        },
    )
    result = _run(plan=plan, client=client)
    assert [item.cap_status for item in result.scope_results] == [
        CapStatus.BELOW_THRESHOLD,
        CapStatus.CAP_RISK,
    ]
    assert result.manifest.cap_risk_scope_count == 1

    above_plan = _small_plan(
        tmp_path / "above",
        "nt_state,,dataset-501\nqld_state,,dataset-500-more\n",
    )
    above_client = NoActorApifyClient(
        "fictional-private-token",
        datasets={
            "dataset-501": FakeDatasetClient(
                pages=(tuple({"id": f"c-{index}"} for index in range(501)),)
            ),
            "dataset-500-more": FakeDatasetClient(
                pages=(tuple({"id": f"d-{index}"} for index in range(500)),)
            ),
        },
    )
    above = _run(plan=above_plan, client=above_client)
    assert above.scope_results[0].cap_status is CapStatus.CAP_RISK
    assert above.scope_results[1].cap_status is CapStatus.CAP_RISK
    assert above.manifest.cap_risk_scope_count == 2

    zero_plan = _small_plan(
        tmp_path / "zero",
        "nt_state,,dataset-one\nqld_state,,dataset-two\n",
    )
    zero_client = NoActorApifyClient(
        "fictional-private-token",
        datasets={
            "dataset-one": FakeDatasetClient(pages=(({"id": "one"},),)),
            "dataset-two": FakeDatasetClient(pages=(({"id": "two"},),)),
        },
    )
    zero = _run(plan=zero_plan, client=zero_client)
    assert zero.manifest.cap_risk_scope_count == 0


def test_all_66_configured_scopes_are_processed_without_actor_access(
    tmp_path: Path,
) -> None:
    config = load_search_scope_config(SEARCH_SCOPES_PATH)
    scopes = build_search_scopes(config)
    source_path = tmp_path / "all_sources.csv"
    source_path.write_text(
        "scope_id,run_id,dataset_id\n"
        + "".join(f"{scope.scope_id},,dataset-{scope.scope_id}\n" for scope in scopes),
        encoding="utf-8",
    )
    plan = build_backfill_fetch_plan(
        source_manifest_path=source_path,
        search_scopes_path=SEARCH_SCOPES_PATH,
        output_root=tmp_path / "output",
    )
    datasets = {
        f"dataset-{scope.scope_id}": FakeDatasetClient(
            pages=(({"id": "same-job-in-every-scope", "scope": scope.scope_id},),)
        )
        for scope in scopes
    }
    client = NoActorApifyClient("fictional-private-token", datasets=datasets)

    result = _run(plan=plan, client=client)

    assert plan.source_manifest.expected_scope_count == 66
    assert result.manifest.successful_scope_count == 66
    assert result.manifest.raw_listing_count == 66
    assert result.manifest.combined_jsonl_row_count == 66
    assert len(result.national_raw_path.read_text(encoding="utf-8").splitlines()) == 66
    assert len(client.dataset_requests) == 66
    assert len(result.scope_results_path.read_text(encoding="utf-8").splitlines()) == 67
    assert client.actor_requests == []


def test_token_is_not_persisted_or_emitted_on_failure(tmp_path: Path) -> None:
    token = "fictional-secret-never-persist"
    plan = _small_plan(tmp_path, "nt_state,,missing\n")
    client = NoActorApifyClient(
        token,
        datasets={"missing": FakeDatasetClient(pages=(), exists=False)},
    )
    events: list[str] = []

    result = fetch_full_backfill(
        plan=plan,
        environ={"APIFY_TOKEN": token},
        client_factory=lambda _token: client,
        clock=lambda: FIXED_TIME,
        event_handler=events.append,
    )

    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (result.manifest_path, result.scope_results_path)
    )
    assert token not in persisted
    assert token not in "\n".join(events)
    assert result.scope_results[0].fetch_status is ScopeFetchStatus.FAILED
