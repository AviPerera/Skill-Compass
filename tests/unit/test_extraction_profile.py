"""Validate safe extraction-profile loading and deterministic hashing."""

from pathlib import Path

import pytest

from skill_compass.extraction.errors import ExtractionConfigurationError
from skill_compass.extraction.profile import load_extraction_profile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = PROJECT_ROOT / "profiles/data_analytics/profile.yaml"


def test_valid_profile_loads_with_approved_versions() -> None:
    profile = load_extraction_profile(PROFILE_PATH)

    assert profile.profile_code == "data_analytics"
    assert profile.profile_version == "0.1.0"
    assert profile.requirement_dictionary_version == "0.1.0"
    assert profile.extractor_version == "0.1.0"
    assert profile.extraction_output_schema_version == "0.1.0"
    assert len(profile.profile_hash) == 64


def test_profile_hash_is_deterministic() -> None:
    first = load_extraction_profile(PROFILE_PATH)
    second = load_extraction_profile(PROFILE_PATH)

    assert first.profile_hash == second.profile_hash


def test_unknown_section_name_is_rejected(tmp_path: Path) -> None:
    profile_text = PROFILE_PATH.read_text(encoding="utf-8")
    invalid_text = profile_text.replace("title_clean: 1.0", "source_title: 1.0")
    invalid_path = tmp_path / "unknown_section.yaml"
    invalid_path.write_text(invalid_text, encoding="utf-8")

    with pytest.raises(ExtractionConfigurationError, match="unknown extraction"):
        load_extraction_profile(invalid_path)


@pytest.mark.parametrize("weight", ["-0.1", "1.1"])
def test_invalid_section_weight_is_rejected(tmp_path: Path, weight: str) -> None:
    profile_text = PROFILE_PATH.read_text(encoding="utf-8")
    invalid_text = profile_text.replace("title_clean: 1.0", f"title_clean: {weight}")
    invalid_path = tmp_path / "invalid_weight.yaml"
    invalid_path.write_text(invalid_text, encoding="utf-8")

    with pytest.raises(ExtractionConfigurationError, match="section weights"):
        load_extraction_profile(invalid_path)


def test_executable_yaml_expression_is_rejected(tmp_path: Path) -> None:
    unsafe_path = tmp_path / "unsafe_profile.yaml"
    unsafe_path.write_text(
        "profile_code: !!python/object/apply:os.system ['echo unsafe']\n",
        encoding="utf-8",
    )

    with pytest.raises(ExtractionConfigurationError, match="safe YAML"):
        load_extraction_profile(unsafe_path)
