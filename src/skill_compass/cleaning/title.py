"""Clean canonical job titles without changing their semantic role wording.

This cleaning-layer module applies only conservative text normalization and
must not classify role, seniority, relevance, or occupation families.
"""

from skill_compass.cleaning.text import normalize_inline_text


def clean_title(title_raw: str) -> str:
    """Return a normalized single-line title while preserving meaningful words."""
    return normalize_inline_text(title_raw) or title_raw.strip()
