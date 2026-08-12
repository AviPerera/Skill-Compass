"""Load secret-bearing settings for explicit Apify collection commands.

This configuration-layer module may read the local environment and `.env`, but
must not initialize clients, make requests, log secrets, or affect processing.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, SecretStr

# =============================================================================
# Safe collection settings
# =============================================================================


class CollectionConfigurationError(RuntimeError):
    """Report missing or unusable external collection configuration."""


class ApifySettings(BaseModel):
    """Hold the Apify token without exposing it in representations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token: SecretStr


def load_apify_settings(
    *,
    dotenv_path: Path = Path(".env"),
    environ: Mapping[str, str] | None = None,
) -> ApifySettings:
    """Load `APIFY_TOKEN`, failing before any client or request can be created."""
    if environ is None:
        load_dotenv(dotenv_path=dotenv_path, override=False)
        environ = os.environ

    token = environ.get("APIFY_TOKEN", "").strip()
    if not token:
        raise CollectionConfigurationError(
            "APIFY_TOKEN is required for explicit Apify collection commands"
        )
    return ApifySettings(token=SecretStr(token))
