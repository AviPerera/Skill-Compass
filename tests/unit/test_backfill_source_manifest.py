"""Test private existing-result manifests against authoritative Feature 4C scopes."""

from pathlib import Path

import pytest

from skill_compass.collection.backfill_sources import (
    BackfillSourceManifestError,
    load_backfill_source_manifest,
)
from skill_compass.collection.search_scopes import (
    build_search_scopes,
    load_search_scope_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEARCH_SCOPES_PATH = PROJECT_ROOT / "profiles/data_analytics/search_scopes.yaml"


def _configured_scopes():  # type: ignore[no-untyped-def]
    return build_search_scopes(load_search_scope_config(SEARCH_SCOPES_PATH))


def test_expected_count_and_missing_scopes_are_derived_from_configuration(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "sources.csv"
    manifest_path.write_text(
        "scope_id,run_id,dataset_id\nnt_state,run-nt,\nqld_state,,dataset-qld\n",
        encoding="utf-8",
    )

    manifest = load_backfill_source_manifest(
        manifest_path, configured_scopes=_configured_scopes()
    )

    assert manifest.expected_scope_count == 66
    assert [item.scope_id for item in manifest.references] == ["nt_state", "qld_state"]
    assert len(manifest.missing_scope_ids) == 64
    assert manifest.is_ready is False


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ("unknown_scope,run-1,\n", "unknown scope_id"),
        ("nt_state,run-1,\nnt_state,run-2,\n", "duplicates scope_id"),
        ("nt_state,,\n", "run_id or dataset_id is required"),
    ],
)
def test_unknown_duplicate_and_identifierless_rows_are_rejected(
    tmp_path: Path, rows: str, message: str
) -> None:
    manifest_path = tmp_path / "invalid.csv"
    manifest_path.write_text(
        "scope_id,run_id,dataset_id\n" + rows,
        encoding="utf-8",
    )

    with pytest.raises(BackfillSourceManifestError, match=message):
        load_backfill_source_manifest(
            manifest_path, configured_scopes=_configured_scopes()
        )


def test_configured_order_is_used_instead_of_csv_order(tmp_path: Path) -> None:
    manifest_path = tmp_path / "out_of_order.csv"
    manifest_path.write_text(
        "scope_id,run_id,dataset_id\nqld_state,,dataset-qld\nnt_state,,dataset-nt\n",
        encoding="utf-8",
    )

    manifest = load_backfill_source_manifest(
        manifest_path, configured_scopes=_configured_scopes()
    )

    assert [item.scope_id for item in manifest.references] == ["nt_state", "qld_state"]
