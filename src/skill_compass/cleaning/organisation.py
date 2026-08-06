"""Clean canonical organisation display values conservatively.

This cleaning-layer module normalizes an already mapped company name and must
not infer employer identity from advertiser or recruiter information.
"""

from skill_compass.cleaning.text import normalize_inline_text


def clean_company_name(company_name_raw: str | None) -> str | None:
    """Return a whitespace- and punctuation-normalized company display name."""
    return normalize_inline_text(company_name_raw)
