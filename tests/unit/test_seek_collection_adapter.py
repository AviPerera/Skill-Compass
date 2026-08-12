"""Test the approved SEEK source configuration and raw identity evidence."""

from pathlib import Path

from skill_compass.collection.seek_adapter import (
    count_source_job_ids,
    load_seek_collection_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "sources/apify_seek_current/collection.yaml"


def test_seek_collection_config_uses_approved_actor_and_safe_test_limit() -> None:
    config = load_seek_collection_config(CONFIG_PATH)

    assert config.actor_id == "scrapersdelight/seek-jobs-scraper"
    assert config.connection_test.max_items == 5
    assert config.connection_test.actor_input["maxItems"] == 5
    assert config.cap_warning_threshold == 500
    assert len(config.classifications) == 30


def test_source_job_id_counts_duplicates_when_all_ids_exist() -> None:
    items = (
        {"id": "job-1"},
        {"raw": {"detail": {"id": "job-1"}}},
        {"id": "job-2"},
    )

    counts = count_source_job_ids(items, ("id", "raw/detail/id"))

    assert counts == (2, 1)


def test_source_job_id_counts_are_unknown_when_any_id_is_missing() -> None:
    items = ({"id": "job-1"}, {"title": "No stable identity"})

    counts = count_source_job_ids(items, ("id",))

    assert counts == (None, None)
