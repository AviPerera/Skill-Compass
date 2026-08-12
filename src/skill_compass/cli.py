"""Provide the thin command-line boundary for Skill Compass application services.

This adapter parses arguments and reports safe summaries; it must not contain
mapping, cleaning, extraction, deduplication, or quality business rules.
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Sequence
from pathlib import Path

from skill_compass.collection.apify_client import ApifyCollectionError
from skill_compass.collection.seek_adapter import SeekCollectionConfigurationError
from skill_compass.config.settings import CollectionConfigurationError
from skill_compass.extraction.errors import (
    ExtractionConfigurationError,
    ExtractionInputError,
    ExtractionReconciliationError,
)
from skill_compass.mapping.errors import MappingConfigurationError
from skill_compass.services.apify_connection_test import run_apify_connection_test
from skill_compass.services.clean_csv import ReconciliationError, process_csv
from skill_compass.services.extract_requirements import process_cleaned_csv

# =============================================================================
# Command parsing and safe output
# =============================================================================


def build_parser() -> argparse.ArgumentParser:
    """Build the Skill Compass parser and current explicit subcommands."""
    parser = argparse.ArgumentParser(prog="skill-compass")
    subcommands = parser.add_subparsers(dest="command", required=True)

    clean_csv = subcommands.add_parser(
        "clean-csv", help="map and deterministically clean an explicit source CSV"
    )
    clean_csv.add_argument("--input", type=Path, required=True)
    clean_csv.add_argument("--mapping", type=Path, required=True)
    clean_csv.add_argument("--output-dir", type=Path, required=True)

    extract = subcommands.add_parser(
        "extract-requirements",
        help="extract deterministic requirements from a Feature 2 cleaned CSV",
    )
    extract.add_argument("--input", type=Path, required=True)
    extract.add_argument("--profile", type=Path, required=True)
    extract.add_argument("--dictionary", type=Path, required=True)
    extract.add_argument("--output-dir", type=Path, required=True)

    apify_test = subcommands.add_parser(
        "test-apify-connection",
        help="run the explicit five-item SEEK Actor connection test",
    )
    apify_test.add_argument(
        "--config",
        type=Path,
        default=Path("sources/apify_seek_current/collection.yaml"),
    )
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


def run_extract_requirements(arguments: argparse.Namespace) -> int:
    """Call the extraction service and print a concise privacy-safe summary."""
    try:
        result = process_cleaned_csv(
            input_path=arguments.input,
            profile_path=arguments.profile,
            dictionary_path=arguments.dictionary,
            output_dir=arguments.output_dir,
        )
    except (
        ExtractionConfigurationError,
        ExtractionInputError,
        ExtractionReconciliationError,
        csv.Error,
        OSError,
        ValueError,
    ) as error:
        print(f"extract-requirements failed: {error}")
        return 1

    extraction = result.extraction
    print("extract-requirements completed successfully")
    print(f"Cleaned input jobs: {extraction.input_cleaned_jobs}")
    print(f"Eligible jobs: {extraction.analytically_eligible_jobs}")
    print(f"Skipped jobs: {extraction.skipped_jobs}")
    print(f"Job-requirement matches: {len(extraction.job_requirement_matches)}")
    print(f"Evidence rows: {len(extraction.evidence)}")
    print("Reconciliation: PASS")
    print(f"Output directory: {result.output_dir}")
    return 0


def run_test_apify_connection(arguments: argparse.Namespace) -> int:
    """Run only the bounded Apify test and print no source records or secrets."""
    try:
        response = run_apify_connection_test(config_path=arguments.config)
    except (
        ApifyCollectionError,
        CollectionConfigurationError,
        SeekCollectionConfigurationError,
        OSError,
        ValueError,
    ) as error:
        print(f"test-apify-connection failed: {error}")
        return 1

    result = response.result
    print("=" * 60)
    print("SKILL COMPASS — APIFY CONNECTION TEST")
    print("=" * 60)
    print()
    print("Actor connection: PASS")
    print(f"Run status: {result.status}")
    print(f"Run ID: {result.run_id}")
    print(f"Dataset ID: {result.dataset_id}")
    print(f"Items retrieved: {result.returned_item_count}")
    print(f"Cap assessment: {result.cap_status.value}")
    print()
    print("No processing or analysis was executed.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch one parsed command and return its process exit code."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "clean-csv":
        return run_clean_csv(arguments)
    if arguments.command == "extract-requirements":
        return run_extract_requirements(arguments)
    if arguments.command == "test-apify-connection":
        return run_test_apify_connection(arguments)
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
