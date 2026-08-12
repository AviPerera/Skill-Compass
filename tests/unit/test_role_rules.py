"""Test safe governed role-rule loading and deterministic version metadata."""

from pathlib import Path

import pytest

from skill_compass.classification.config import (
    APPROVED_ROLE_CODES,
    load_role_rules,
)
from skill_compass.classification.errors import RoleConfigurationError

RULES_PATH = Path("profiles/data_analytics/role_rules.yaml")


def test_role_rules_define_only_the_governed_dashboard_taxonomy() -> None:
    rules = load_role_rules(RULES_PATH)

    assert tuple(role.role_group_code for role in rules.roles) == APPROVED_ROLE_CODES
    assert tuple(role.role_group_label for role in rules.roles) == (
        "Data Analyst",
        "Business Analyst",
        "BI Analyst",
        "Reporting Analyst",
        "Data Scientist",
    )
    assert rules.role_rules_version == "0.1.0"
    assert len(rules.role_rules_hash) == 64


def test_role_rules_hash_is_stable_for_repeated_loading() -> None:
    first = load_role_rules(RULES_PATH)
    second = load_role_rules(RULES_PATH)

    assert first == second
    assert first.role_rules_hash == second.role_rules_hash


def test_role_rules_reject_executable_yaml_tags(tmp_path: Path) -> None:
    rules_path = tmp_path / "unsafe.yaml"
    rules_path.write_text(
        "!!python/object/apply:builtins.eval ['1 + 1']", encoding="utf-8"
    )

    with pytest.raises(RoleConfigurationError, match="safe YAML"):
        load_role_rules(rules_path)
