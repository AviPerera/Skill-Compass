"""Test governed relevance configuration in the unit-test layer.

These tests validate safe loading and stable metadata and must not classify
jobs, read private data, or change governed profile policy.
"""

from pathlib import Path

import pytest

from skill_compass.classification.errors import RelevanceConfigurationError
from skill_compass.classification.relevance_config import load_relevance_rules

RULES_PATH = Path("profiles/data_analytics/relevance_rules.yaml")


def test_relevance_rules_define_governed_profile_policy() -> None:
    rules = load_relevance_rules(RULES_PATH)

    assert rules.profile_code == "data_analytics"
    assert rules.approved_role_codes == (
        "data_analyst",
        "business_analyst",
        "bi_analyst",
        "reporting_analyst",
        "data_scientist",
    )
    assert rules.relevance_classifier_version == "0.1.0"
    assert rules.relevance_rules_version == "0.1.0"
    assert rules.thresholds.exclusion_score < rules.thresholds.inclusion_score
    assert len(rules.relevance_rules_hash) == 64


def test_relevance_rule_hash_is_stable() -> None:
    first = load_relevance_rules(RULES_PATH)
    second = load_relevance_rules(RULES_PATH)

    assert first == second
    assert first.relevance_rules_hash == second.relevance_rules_hash


def test_relevance_rules_reject_executable_yaml_tags(tmp_path: Path) -> None:
    rules_path = tmp_path / "unsafe.yaml"
    rules_path.write_text(
        "!!python/object/apply:builtins.eval ['1 + 1']", encoding="utf-8"
    )

    with pytest.raises(RelevanceConfigurationError, match="safe YAML"):
        load_relevance_rules(rules_path)
