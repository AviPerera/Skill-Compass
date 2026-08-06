"""Normalize canonical text conservatively while preserving useful structure.

This cleaning-layer module handles Unicode and whitespace only and must not
classify roles, infer source fields, or read and write files.
"""

from __future__ import annotations

import re
import unicodedata

# =============================================================================
# Conservative character and whitespace normalization
# =============================================================================


PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "\u00a0": " ",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
    }
)


def normalize_text(value: str | None) -> str | None:
    """Normalize Unicode, line endings, and redundant whitespace."""
    if value is None:
        return None

    normalized = unicodedata.normalize("NFC", value).translate(PUNCTUATION_TRANSLATION)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    lines = [
        re.sub(r"[\t\f\v ]+", " ", line).strip() for line in normalized.split("\n")
    ]
    compact_lines: list[str] = []
    previous_blank = True
    for line in lines:
        if line:
            compact_lines.append(line)
            previous_blank = False
        elif not previous_blank:
            compact_lines.append("")
            previous_blank = True

    while compact_lines and not compact_lines[-1]:
        compact_lines.pop()
    result = "\n".join(compact_lines).strip()
    return result or None


def normalize_inline_text(value: str | None) -> str | None:
    """Normalize text and collapse its structure to one readable line."""
    normalized = normalize_text(value)
    return " ".join(normalized.split()) if normalized else None
