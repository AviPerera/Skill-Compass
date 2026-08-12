"""Test secret-safe settings used only by explicit collection commands."""

from pathlib import Path

import pytest

from skill_compass.config.settings import (
    CollectionConfigurationError,
    load_apify_settings,
)


def test_missing_apify_token_fails_with_safe_message(tmp_path: Path) -> None:
    with pytest.raises(CollectionConfigurationError, match="APIFY_TOKEN is required"):
        load_apify_settings(dotenv_path=tmp_path / ".env", environ={})


def test_token_is_masked_in_settings_representation() -> None:
    token = "apify_api_secret-test-value"

    settings = load_apify_settings(environ={"APIFY_TOKEN": token})

    assert settings.token.get_secret_value() == token
    assert token not in repr(settings)
