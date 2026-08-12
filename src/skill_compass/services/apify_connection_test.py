"""Coordinate the explicit, bounded Apify connection-test use case.

This application service loads configuration and calls collection only when
explicitly requested. It must not invoke processing, analysis, or persistence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from skill_compass.collection.apify_client import (
    ApifyCollectionResponse,
    collect_connection_test,
)
from skill_compass.collection.seek_adapter import load_seek_collection_config
from skill_compass.config.settings import load_apify_settings

# =============================================================================
# Explicit connection-test orchestration
# =============================================================================


def run_apify_connection_test(
    *,
    config_path: Path,
    dotenv_path: Path = Path(".env"),
    environ: Mapping[str, str] | None = None,
    client_factory: Callable[[str], Any] | None = None,
) -> ApifyCollectionResponse:
    """Load settings before creating a client, then run only the tiny test."""
    settings = load_apify_settings(dotenv_path=dotenv_path, environ=environ)
    config = load_seek_collection_config(config_path)
    if client_factory is None:
        return collect_connection_test(settings=settings, config=config)
    return collect_connection_test(
        settings=settings,
        config=config,
        client_factory=client_factory,
    )
