"""Provide the thin command-line boundary for Skill Compass application services.

This adapter parses arguments and reports safe summaries; it must not contain
mapping, cleaning, deduplication, or quality business rules.
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Sequence
from pathlib import Path

from skill_compass.mapping.errors import MappingConfigurationError
from skill_compass.services.clean_csv import ReconciliationError, process_csv

# =============================================================================
# Command parsing and safe output
# =============================================================================


def build_parser() -> argparse.ArgumentParser:
    """Build the Skill Compass command parser and clean-csv subcommand."""
    parser = argparse.ArgumentParser(prog="skill-compass")
    subcommands = parser.add_subparsers(dest="command", required=True)

    clean_csv = subcommands.add_parser(
        "clean-csv", help="map and deterministically clean an explicit source CSV"
    )
    clean_csv.add_argument("--input", type=Path, required=True)
    clean_csv.add_argument("--mapping", type=Path, required=True)
    clean_csv.add_argument("--output-dir", type=Path, required=True)
    return parser


def run_clean_csv(arguments: argparse.Namespace) -> int:
    """Call the reusable service and print a concise privacy-safe run summary."""
    try:
        result = process_csv(
            input_path=arguments.input,
            mapping_path=arguments.mapping,
            output_dir=arguments.output_dir,
        )
    except (
        MappingConfigurationError,
        ReconciliationError,
        FileNotFoundError,
        UnicodeError,
        csv.Error,
        OSError,
        ValueError,
    ) as error:
        print(f"clean-csv failed: {error}")
        return 1

    print("clean-csv completed successfully")
    print(f"Input rows: {result.input_rows}")
    print(f"Cleaned rows: {len(result.cleaned_jobs)}")
    print(f"Rejected rows: {result.total_rejected_rows}")
    print("Reconciliation: PASS")
    print(f"Output directory: {result.output_dir}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch one parsed command and return its process exit code."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "clean-csv":
        return run_clean_csv(arguments)
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
