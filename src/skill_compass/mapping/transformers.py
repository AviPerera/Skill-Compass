"""Implement allowlisted scalar transformers for canonical source mapping.

These functions convert individual source values only and must not encode CSV
I/O, field precedence, cleaning, or analytical business rules.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable

# =============================================================================
# Transformer implementations
# =============================================================================


def transform_text(value: str) -> str | None:
    """Strip a source string and return null for empty values."""
    normalized = value.strip()
    return normalized or None


def transform_boolean(value: str) -> bool | None:
    """Convert supported source boolean labels without guessing."""
    normalized = value.strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def transform_decimal(value: str) -> Decimal | None:
    """Convert a structured numeric source value to Decimal."""
    normalized = value.strip().replace(",", "")
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


SCALAR_TRANSFORMERS: dict[str, Callable[[str], object]] = {
    "boolean": transform_boolean,
    "decimal": transform_decimal,
    "text": transform_text,
}

COLLECTION_TRANSFORMER = "collect_text"
ALLOWED_TRANSFORMERS = frozenset((*SCALAR_TRANSFORMERS, COLLECTION_TRANSFORMER))


# =============================================================================
# Transformer dispatch
# =============================================================================


def apply_scalar_transformer(name: str, value: str) -> object:
    """Apply one previously validated scalar transformer by name."""
    return SCALAR_TRANSFORMERS[name](value)


def collect_text(values: tuple[str, ...]) -> tuple[str, ...]:
    """Return ordered non-empty stripped values from a source field group."""
    return tuple(normalized for value in values if (normalized := value.strip()))
