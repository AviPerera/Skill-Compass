"""Calculate deterministic hashes from process-relevant cleaned job content.

This cleaning-layer module canonicalizes analytical content and must exclude
observation-only row, scrape, promotion, and mapping-provenance values.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from decimal import Decimal


def canonical_value(value: object) -> object:
    """Convert supported typed values to deterministic JSON-compatible values."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [canonical_value(item) for item in value]
    return value


def calculate_content_hash(content: Mapping[str, object]) -> str:
    """Hash a stable JSON serialization of documented process-relevant fields."""
    canonical_content = {key: canonical_value(content[key]) for key in sorted(content)}
    serialized = json.dumps(
        canonical_content,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
