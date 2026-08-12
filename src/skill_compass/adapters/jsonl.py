"""Read raw source JSONL records into flattened source-field mappings.

This outer adapter belongs to the file-input boundary. It owns strict JSONL
parsing, deterministic row numbering, and slash-delimited path flattening; it
must not map canonical fields, clean values, deduplicate jobs, or invoke a
collection source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# =============================================================================
# Typed JSONL reader results
# =============================================================================


@dataclass(frozen=True, slots=True)
class JsonlSourceRow:
    """Represent one JSON object and its deterministic one-based line number."""

    source_row_number: int
    values: dict[str, str]


@dataclass(frozen=True, slots=True)
class JsonlReadResult:
    """Represent parsed source rows plus privacy-safe structural metadata."""

    encoding: str
    source_fields: tuple[str, ...]
    rows: tuple[JsonlSourceRow, ...]


# =============================================================================
# Deterministic JSON path flattening
# =============================================================================


def _json_scalar_text(value: object) -> str:
    """Serialize one JSON scalar to the text boundary expected by mapping."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def flatten_json_object(document: dict[str, Any]) -> dict[str, str]:
    """Flatten nested objects and arrays into slash-delimited source paths."""
    flattened: dict[str, str] = {}

    def visit(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}/{key}" if path else key
                visit(child, child_path)
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                child_path = f"{path}/{index}" if path else str(index)
                visit(child, child_path)
            return
        if path in flattened:
            raise ValueError(f"source JSON path collision: {path}")
        flattened[path] = _json_scalar_text(value)

    visit(document, "")
    return flattened


def _reject_nonstandard_constant(value: str) -> None:
    """Reject NaN and infinity tokens, which are not valid JSON values."""
    raise ValueError(f"non-standard JSON constant: {value}")


# =============================================================================
# Strict JSONL input adapter
# =============================================================================


def read_source_jsonl(path: Path) -> JsonlReadResult:
    """Read UTF-8 JSONL objects without exposing source values in errors."""
    rows: list[JsonlSourceRow] = []
    source_fields: set[str] = set()

    with path.open("r", encoding="utf-8") as input_file:
        for source_row_number, line in enumerate(input_file, start=1):
            if not line.strip():
                raise ValueError(f"source JSONL line {source_row_number} is blank")
            try:
                document = json.loads(line, parse_constant=_reject_nonstandard_constant)
            except (json.JSONDecodeError, ValueError) as error:
                raise ValueError(
                    f"source JSONL line {source_row_number} is not valid JSON"
                ) from error
            if not isinstance(document, dict):
                raise ValueError(
                    f"source JSONL line {source_row_number} must be a JSON object"
                )

            values = flatten_json_object(document)
            source_fields.update(values)
            rows.append(
                JsonlSourceRow(
                    source_row_number=source_row_number,
                    values=values,
                )
            )

    if not rows:
        raise ValueError("source JSONL must contain at least one JSON object")

    return JsonlReadResult(
        encoding="utf-8",
        source_fields=tuple(sorted(source_fields)),
        rows=tuple(rows),
    )
