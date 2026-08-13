"""Provide the thin local Feature 8 dashboard-visual demo entry point.

This script parses local paths and delegates to the reusable demo service. It
must not calculate analytics, render charts directly, or invoke external APIs.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from skill_compass.services.demo_dashboard import (
    DEFAULT_DICTIONARY,
    DEFAULT_INPUT_DIR,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROFILE,
    DEFAULT_REFERENCE_WORKBOOK,
    DEFAULT_ROLE_RULES,
    DEFAULT_SENIORITY_RULES,
    run_dashboard_demo_command,
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit local-only dashboard demonstration options."""
    parser = argparse.ArgumentParser(
        description="Generate all approved static Skill Compass dashboard visuals."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY)
    parser.add_argument("--role-rules", type=Path, default=DEFAULT_ROLE_RULES)
    parser.add_argument("--seniority-rules", type=Path, default=DEFAULT_SENIORITY_RULES)
    parser.add_argument(
        "--reference-workbook", type=Path, default=DEFAULT_REFERENCE_WORKBOOK
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Delegate the local demonstration and return its controlled exit code."""
    arguments = build_parser().parse_args(argv)
    return run_dashboard_demo_command(
        input_dir=arguments.input_dir,
        output_dir=arguments.output_dir,
        profile_path=arguments.profile,
        dictionary_path=arguments.dictionary,
        role_rules_path=arguments.role_rules,
        seniority_rules_path=arguments.seniority_rules,
        reference_workbook=arguments.reference_workbook,
    )


if __name__ == "__main__":
    raise SystemExit(main())
