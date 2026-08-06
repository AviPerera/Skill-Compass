"""Convert canonical HTML descriptions into deterministic readable plain text.

This cleaning-layer parser preserves block and list boundaries and must not
execute markup, fetch resources, or inspect source-specific field names.
"""

from __future__ import annotations

from html.parser import HTMLParser

from skill_compass.cleaning.text import normalize_text

# =============================================================================
# Safe structural HTML parsing
# =============================================================================


BLOCK_TAGS = frozenset(
    {"article", "blockquote", "div", "h1", "h2", "h3", "h4", "h5", "h6", "p", "section"}
)
IGNORED_TAGS = frozenset({"script", "style"})


class StructuredTextParser(HTMLParser):
    """Collect visible HTML text with deterministic block separators."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record structural boundaries and enter ignored markup."""
        del attrs
        normalized_tag = tag.casefold()
        if normalized_tag in IGNORED_TAGS:
            self.ignored_depth += 1
            return
        if self.ignored_depth:
            return
        if normalized_tag in BLOCK_TAGS or normalized_tag in {"br", "ul", "ol"}:
            self.parts.append("\n")
        elif normalized_tag == "li":
            self.parts.append("\n- ")

    def handle_endtag(self, tag: str) -> None:
        """Close ignored markup and append block separators."""
        normalized_tag = tag.casefold()
        if normalized_tag in IGNORED_TAGS:
            self.ignored_depth = max(0, self.ignored_depth - 1)
            return
        if not self.ignored_depth and (
            normalized_tag in BLOCK_TAGS or normalized_tag in {"li", "ul", "ol"}
        ):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        """Collect visible text outside scripts and styles."""
        if not self.ignored_depth:
            self.parts.append(data)


def html_to_text(value: str | None) -> str | None:
    """Convert an HTML fragment to normalized plain text without executing it."""
    if not value or not value.strip():
        return None

    parser = StructuredTextParser()
    parser.feed(value)
    parser.close()
    return normalize_text("".join(parser.parts))
