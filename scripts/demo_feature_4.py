"""Provide the thin live Feature 4 existing-data demonstration entry point.

This script parses safe local options and calls the reusable demonstration
service. It must not contain Apify retrieval, reporting, or processing logic.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from skill_compass.collection.search_scopes import DEFAULT_SEARCH_SCOPES_PATH
from skill_compass.services.demo_feature_4 import run_feature_4_demo_command
from skill_compass.services.fetch_backfill import (
    DEFAULT_BACKFILL_FETCH_ROOT,
    DEFAULT_SEEK_COLLECTION_PATH,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the live read-only demonstration options."""
    parser = argparse.ArgumentParser(
        description="Demonstrate Feature 4 using existing Apify datasets only."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="deliberately re-download datasets already fetched locally",
    )
    parser.add_argument(
        "--actor-config", type=Path, default=DEFAULT_SEEK_COLLECTION_PATH
    )
    parser.add_argument(
        "--search-scopes", type=Path, default=DEFAULT_SEARCH_SCOPES_PATH
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_BACKFILL_FETCH_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Delegate the live demonstration to the shared application service."""
    arguments = build_parser().parse_args(argv)
    return run_feature_4_demo_command(
        force=arguments.force,
        search_scopes_path=arguments.search_scopes,
        actor_config_path=arguments.actor_config,
        output_root=arguments.output_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
