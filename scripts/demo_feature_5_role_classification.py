"""Provide the thin Feature 5 local role-classification demo entry point.

This script parses local paths and delegates to the production demo service; it
must not contain role rules, scoring logic, source collection, or file writing.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from skill_compass.services.demo_feature_5 import (
    DEFAULT_ROLE_INPUT,
    DEFAULT_ROLE_OUTPUT,
    DEFAULT_ROLE_RULES,
    run_feature_5_demo_command,
)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit local input, rules, and output arguments."""
    parser = argparse.ArgumentParser(
        description="Demonstrate explainable role classification on cleaned jobs."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_ROLE_INPUT)
    parser.add_argument("--rules", type=Path, default=DEFAULT_ROLE_RULES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ROLE_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Delegate demonstration execution to the reusable application service."""
    arguments = build_parser().parse_args(argv)
    return run_feature_5_demo_command(
        input_path=arguments.input,
        rules_path=arguments.rules,
        output_dir=arguments.output_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
