"""Provide the manual safety-gated entry point for the national backfill.

This script only parses arguments, calls the reusable service command, and
returns its exit code. It must not implement scope logic or invoke Apify itself.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from skill_compass.services.full_collection import (
    DEFAULT_ACTOR_CONFIG_PATH,
    DEFAULT_FULL_COLLECTION_ROOT,
    DEFAULT_SEARCH_SCOPES_PATH,
    run_full_collection_command,
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit dry-run/execute arguments for the paid operation."""
    parser = argparse.ArgumentParser(
        description="Plan or execute the one-time full national SEEK backfill."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--search-scopes", type=Path, default=DEFAULT_SEARCH_SCOPES_PATH
    )
    parser.add_argument("--actor-config", type=Path, default=DEFAULT_ACTOR_CONFIG_PATH)
    parser.add_argument(
        "--output-root", type=Path, default=DEFAULT_FULL_COLLECTION_ROOT
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and delegate to the shared full-collection service."""
    arguments = build_parser().parse_args(argv)
    return run_full_collection_command(
        dry_run=arguments.dry_run,
        execute=arguments.execute,
        resume=arguments.resume,
        force=arguments.force,
        search_scopes_path=arguments.search_scopes,
        actor_config_path=arguments.actor_config,
        output_root=arguments.output_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
