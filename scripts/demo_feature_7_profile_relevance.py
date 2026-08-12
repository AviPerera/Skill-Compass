"""Provide the thin Feature 7 local profile-relevance demo entry point.

This script parses local paths and delegates to the production demo service; it
must not contain relevance rules, scoring logic, collection, or file writing.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from skill_compass.services.demo_feature_7 import (
    DEFAULT_RELEVANCE_INPUT,
    DEFAULT_RELEVANCE_OUTPUT,
    DEFAULT_RELEVANCE_RULES,
    run_feature_7_demo_command,
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit local input, rules, and output arguments."""
    parser = argparse.ArgumentParser(
        description="Demonstrate explainable profile relevance on processed jobs."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_RELEVANCE_INPUT)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RELEVANCE_RULES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RELEVANCE_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Delegate demonstration execution to the reusable application service."""
    arguments = build_parser().parse_args(argv)
    return run_feature_7_demo_command(
        input_dir=arguments.input_dir,
        rules_path=arguments.rules,
        output_dir=arguments.output_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
