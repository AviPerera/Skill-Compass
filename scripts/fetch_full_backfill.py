"""Provide the thin entry point for existing national dataset retrieval.

This script only parses arguments and calls the reusable Feature 4B service. It
must not invoke an Actor, fetch pages directly, combine files, or process jobs.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from skill_compass.collection.search_scopes import DEFAULT_SEARCH_SCOPES_PATH
from skill_compass.services.fetch_backfill import (
    DEFAULT_BACKFILL_FETCH_ROOT,
    DEFAULT_SEEK_COLLECTION_PATH,
    run_fetch_backfill_command,
)


def build_parser() -> argparse.ArgumentParser:
    """Build manifest, dry-run, resume-default, and deliberate force options."""
    parser = argparse.ArgumentParser(
        description="Fetch existing Apify backfill datasets without an Actor run."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--include-all-successful-runs",
        action="store_true",
        help="append datasets from all other successful runs of the configured Actor",
    )
    parser.add_argument(
        "--actor-config",
        type=Path,
        default=DEFAULT_SEEK_COLLECTION_PATH,
        help="source configuration containing the approved Actor ID",
    )
    parser.add_argument(
        "--search-scopes", type=Path, default=DEFAULT_SEARCH_SCOPES_PATH
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_BACKFILL_FETCH_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and delegate to the shared no-Actor batch service."""
    arguments = build_parser().parse_args(argv)
    if arguments.dry_run and arguments.force:
        print("--force cannot be combined with --dry-run. Actor invocation: NO")
        return 2
    return run_fetch_backfill_command(
        source_manifest_path=arguments.manifest,
        dry_run=arguments.dry_run,
        force=arguments.force,
        include_all_successful_runs=arguments.include_all_successful_runs,
        actor_config_path=arguments.actor_config,
        search_scopes_path=arguments.search_scopes,
        output_root=arguments.output_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
