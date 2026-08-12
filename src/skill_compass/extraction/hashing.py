"""Calculate deterministic hashes for extraction configuration values.

This extraction utility canonicalizes declarative configuration only and must
not hash private job text, read files, or implement matching behaviour.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal


def canonical_hash_value(value: object) -> object:
    """Convert supported values into stable JSON-compatible structures."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return {
            str(key): canonical_hash_value(value[key]) for key in sorted(value, key=str)
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [canonical_hash_value(item) for item in value]
    return value


def canonical_sha256(value: object) -> str:
    """Hash canonical compact JSON with UTF-8 and sorted mapping keys."""
    serialized = json.dumps(
        canonical_hash_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
