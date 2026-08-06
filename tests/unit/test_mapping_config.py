"""Validate the declarative source-mapping contract and its safety boundary."""

from pathlib import Path

import pytest
import yaml

from skill_compass.mapping.config import load_mapping_config
from skill_compass.mapping.errors import MappingConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = PROJECT_ROOT / "sources/apify_seek_current/source_mapping.yaml"


def test_valid_mapping_loads_with_approved_versions() -> None:
    mapping = load_mapping_config(MAPPING_PATH)

    assert mapping.source_code == "apify_seek_current"
    assert mapping.mapping_version == "0.1.0"
    assert mapping.canonical_schema_version == "0.1.0"
    assert len(mapping.mapping_config_hash) == 64


def test_mapping_hash_is_deterministic() -> None:
    first = load_mapping_config(MAPPING_PATH)
    second = load_mapping_config(MAPPING_PATH)

    assert first.mapping_config_hash == second.mapping_config_hash


def test_unknown_transformer_is_rejected(tmp_path: Path) -> None:
    mapping_text = MAPPING_PATH.read_text(encoding="utf-8")
    invalid_text = mapping_text.replace(
        "transformer: text", "transformer: unknown_transformer", 1
    )
    invalid_path = tmp_path / "unknown_transformer.yaml"
    invalid_path.write_text(invalid_text, encoding="utf-8")

    with pytest.raises(MappingConfigurationError, match="unknown transformer"):
        load_mapping_config(invalid_path)


def test_executable_yaml_expression_is_rejected(tmp_path: Path) -> None:
    unsafe_path = tmp_path / "unsafe.yaml"
    unsafe_path.write_text(
        "source_code: !!python/object/apply:os.system ['echo unsafe']\n",
        encoding="utf-8",
    )

    with pytest.raises(MappingConfigurationError, match="safe YAML"):
        load_mapping_config(unsafe_path)


def test_required_canonical_fields_are_validated(tmp_path: Path) -> None:
    document = yaml.safe_load(MAPPING_PATH.read_text(encoding="utf-8"))
    del document["fields"]["source_job_id"]
    invalid_path = tmp_path / "missing_required_field.yaml"
    invalid_path.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(MappingConfigurationError, match="source_job_id"):
        load_mapping_config(invalid_path)
