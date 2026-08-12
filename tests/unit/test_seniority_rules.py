"""Test safe governed seniority-rule loading and version metadata."""

from pathlib import Path

import pytest

from skill_compass.classification.errors import SeniorityConfigurationError
from skill_compass.classification.seniority_config import (
    APPROVED_SENIORITY_CODES,
    load_seniority_rules,
)

RULES_PATH = Path("profiles/data_analytics/seniority_rules.yaml")


def test_seniority_rules_define_the_governed_order_and_graduate_flag() -> None:
    rules = load_seniority_rules(RULES_PATH)

    assert tuple(level.seniority_code for level in rules.levels) == (
        APPROVED_SENIORITY_CODES
    )
    assert tuple(level.seniority_label for level in rules.levels) == (
        "Entry-level",
        "Junior",
        "Mid-level",
        "Senior",
    )
    assert tuple(level.rank_order for level in rules.levels) == (1, 2, 3, 4)
    assert tuple(level.graduate_level_flag for level in rules.levels) == (
        True,
        True,
        False,
        False,
    )
    assert rules.seniority_rules_version == "0.1.0"
    assert len(rules.seniority_rules_hash) == 64


def test_seniority_rules_hash_is_stable_for_repeated_loading() -> None:
    first = load_seniority_rules(RULES_PATH)
    second = load_seniority_rules(RULES_PATH)

    assert first == second
    assert first.seniority_rules_hash == second.seniority_rules_hash


def test_seniority_rules_reject_executable_yaml_tags(tmp_path: Path) -> None:
    rules_path = tmp_path / "unsafe.yaml"
    rules_path.write_text(
        "!!python/object/apply:builtins.eval ['1 + 1']", encoding="utf-8"
    )

    with pytest.raises(SeniorityConfigurationError, match="safe YAML"):
        load_seniority_rules(rules_path)
