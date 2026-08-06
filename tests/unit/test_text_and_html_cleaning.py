"""Test conservative Unicode, whitespace, title, organisation, and HTML cleaning."""

from skill_compass.cleaning.html import html_to_text
from skill_compass.cleaning.organisation import clean_company_name
from skill_compass.cleaning.text import normalize_text
from skill_compass.cleaning.title import clean_title


def test_unicode_and_whitespace_normalization_preserves_paragraphs() -> None:
    value = "  Alpha\u00a0\u2014  Beta\r\n\r\n  Gamma  "

    assert normalize_text(value) == "Alpha - Beta\n\nGamma"


def test_title_cleaning_is_conservative() -> None:
    title = "  Senior\u00a0Data\u2013Analyst  "

    assert clean_title(title) == "Senior Data-Analyst"


def test_organisation_cleaning_does_not_infer_another_identity() -> None:
    assert clean_company_name("  Example\u00a0Company  ") == "Example Company"
    assert clean_company_name(None) is None


def test_html_to_text_preserves_blocks_and_removes_unsafe_markup() -> None:
    markup = (
        "<h2>Role</h2><p>Build reports.</p><ul><li>SQL</li><li>BI</li></ul>"
        "<script>private_code()</script><style>.hidden {}</style>"
    )

    cleaned = html_to_text(markup)

    assert cleaned is not None
    assert "Role" in cleaned
    assert "Build reports." in cleaned
    assert "- SQL" in cleaned
    assert "- BI" in cleaned
    assert "private_code" not in cleaned
    assert "hidden" not in cleaned
    assert cleaned == html_to_text(markup)
