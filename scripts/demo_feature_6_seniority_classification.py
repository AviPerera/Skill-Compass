"""Provide the thin Feature 6 local seniority-classification demo entry point.

This script parses local paths and delegates to the production demo service; it
must not contain rules, scoring logic, source collection, or file writing.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from skill_compass.services.demo_feature_6 import (
    DEFAULT_SENIORITY_INPUT,
    DEFAULT_SENIORITY_OUTPUT,
    DEFAULT_SENIORITY_RULES,
    run_feature_6_demo_command,
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit local input, rules, and output arguments."""
    parser = argparse.ArgumentParser(
        description="Demonstrate explainable seniority classification on cleaned jobs."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_SENIORITY_INPUT)
    parser.add_argument("--rules", type=Path, default=DEFAULT_SENIORITY_RULES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_SENIORITY_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Delegate demonstration execution to the reusable application service."""
    arguments = build_parser().parse_args(argv)
    return run_feature_6_demo_command(
        input_path=arguments.input,
        rules_path=arguments.rules,
        output_dir=arguments.output_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
