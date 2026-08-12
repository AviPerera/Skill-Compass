"""Match configured requirement aliases within separate cleaned text sections.

This deterministic extraction layer preserves bounded evidence and must not
read files, inspect non-content job fields, aggregate demand, or render charts.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from skill_compass.extraction.hashing import canonical_sha256
from skill_compass.schemas.extraction import (
    ExtractionProfile,
    RequirementAlias,
    RequirementDictionary,
    RequirementEvidence,
)
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Stable matcher policy
# =============================================================================


SECTION_ORDER = {
    "title_clean": 0,
    "summary_text_clean": 1,
    "bullet_points_clean": 2,
    "description_text_clean": 3,
}
EXTRACTOR_POLICY = {
    "normalization": "unicode_nfc_whitespace_v1",
    "overlap_policy": "longest_valid_span_first",
    "negative_context_policy": "literal_terms_and_conservative_patterns_v1",
    "snippet_markers": "double_square_brackets",
    "canonical_alias_score_multiplier": "1.0",
    "alternate_alias_score_multiplier": "0.9",
}
EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])",
    re.IGNORECASE,
)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")
NEGATIVE_BEFORE_PATTERN = re.compile(
    r"(?:\bno|\bwithout(?:\s+using)?|\bdo(?:es)?\s+not\s+require)\s+$",
    re.IGNORECASE,
)
NEGATIVE_AFTER_PATTERN = re.compile(
    r"^\s+(?:experience\s+)?(?:is\s+)?not\s+required\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AliasCandidate:
    """Hold one literal alias span before overlap and context decisions."""

    alias: RequirementAlias
    start: int
    end: int
    matched_text: str


@dataclass(frozen=True, slots=True)
class JobEvidenceResult:
    """Return accepted and suppressed evidence for one typed cleaned job."""

    evidence: tuple[RequirementEvidence, ...]
    suppressed_negative_context_count: int
    extractor_config_hash: str


def extractor_config_hash(profile: ExtractionProfile) -> str:
    """Hash the documented matcher policy plus profile-controlled settings."""
    return canonical_sha256(
        {
            **EXTRACTOR_POLICY,
            "extractor_version": profile.extractor_version,
            "section_weights": profile.section_weights,
            "confidence_thresholds": profile.confidence_thresholds.model_dump(
                mode="python"
            ),
            "negative_context_window": profile.negative_context_window,
            "evidence_snippet_length": profile.evidence_snippet_length,
        }
    )


# =============================================================================
# Literal alias matching and overlap control
# =============================================================================


def normalized_alias_pattern(alias: RequirementAlias) -> re.Pattern[str]:
    """Compile an escaped literal alias with explicit whitespace and boundaries."""
    escaped_words = [re.escape(word) for word in alias.alias_text.split()]
    literal_pattern = r"\s+".join(escaped_words)
    if alias.match_type == "exact":
        pattern = rf"^\s*{literal_pattern}\s*$"
    elif alias.require_word_boundary:
        pattern = rf"(?<!\w){literal_pattern}(?!\w)"
    else:
        pattern = literal_pattern
    flags = 0 if alias.case_sensitive else re.IGNORECASE
    return re.compile(pattern, flags)


def alias_candidates(
    text: str, aliases: tuple[RequirementAlias, ...]
) -> tuple[AliasCandidate, ...]:
    """Find all literal candidates and order longest spans before shorter overlaps."""
    candidates = [
        AliasCandidate(alias, match.start(), match.end(), match.group())
        for alias in aliases
        for match in normalized_alias_pattern(alias).finditer(text)
    ]
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                -(candidate.end - candidate.start),
                candidate.start,
                candidate.alias.sort_order,
                candidate.alias.alias_text.casefold(),
            ),
        )
    )


def overlaps_existing(
    candidate: AliasCandidate, accepted_spans: list[tuple[int, int]]
) -> bool:
    """Return whether a candidate intersects a previously accepted longer span."""
    return any(
        candidate.start < accepted_end and candidate.end > accepted_start
        for accepted_start, accepted_end in accepted_spans
    )


def negative_context_found(
    text: str, candidate: AliasCandidate, window_size: int
) -> bool:
    """Detect conservative negation immediately around one alias occurrence."""
    before = text[max(0, candidate.start - window_size) : candidate.start]
    after = text[candidate.end : min(len(text), candidate.end + window_size)]
    before_normalized = " ".join(before.casefold().split()) + " "
    after_normalized = " " + " ".join(after.casefold().split())

    if NEGATIVE_BEFORE_PATTERN.search(before_normalized):
        return True
    if NEGATIVE_AFTER_PATTERN.search(after_normalized):
        return True

    before_edge = before_normalized.rstrip()
    after_edge = after_normalized.lstrip()
    return any(
        before_edge.endswith(term.casefold()) or after_edge.startswith(term.casefold())
        for term in candidate.alias.negative_context_terms
    )


# =============================================================================
# Safe deterministic evidence construction
# =============================================================================


def redact_snippet(value: str) -> str:
    """Redact predictable contact patterns from bounded evidence text."""
    without_email = EMAIL_PATTERN.sub("[redacted-email]", value)
    return PHONE_PATTERN.sub("[redacted-phone]", without_email)


def evidence_snippet(
    text: str,
    start: int,
    end: int,
    maximum: int,
    *,
    avoid_full_section: bool = False,
) -> str:
    """Return a bounded deterministic context window with marked matched text."""
    matched = text[start:end]
    marker_length = 4
    available_context = max(0, maximum - len(matched) - marker_length)
    left_budget = available_context // 2
    right_budget = available_context - left_budget
    snippet_start = max(0, start - left_budget)
    snippet_end = min(len(text), end + right_budget)
    if (
        avoid_full_section
        and snippet_start == 0
        and snippet_end == len(text)
        and len(text) > len(matched)
    ):
        if start > 0:
            snippet_start = 1
        elif end < len(text):
            snippet_end = len(text) - 1
    prefix = "..." if snippet_start > 0 else ""
    suffix = "..." if snippet_end < len(text) else ""
    value = (
        f"{prefix}{text[snippet_start:start]}[[{matched}]]"
        f"{text[end:snippet_end]}{suffix}"
    )
    return redact_snippet(value)[:maximum]


def normalized_section_text(value: str) -> str:
    """Normalize Unicode and whitespace without losing stable source offsets."""
    normalized = unicodedata.normalize("NFC", value)
    return normalized.replace("\r\n", "\n").replace("\r", "\n")


def content_sections(job: CleanedJob) -> tuple[tuple[str, int, str], ...]:
    """Return only approved cleaned content sections in deterministic order."""
    sections: list[tuple[str, int, str]] = [("title_clean", 0, job.title_clean)]
    if job.summary_text_clean:
        sections.append(("summary_text_clean", 0, job.summary_text_clean))
    sections.extend(
        ("bullet_points_clean", position, bullet)
        for position, bullet in enumerate(job.bullet_points_clean)
    )
    if job.description_text_clean:
        sections.append(("description_text_clean", 0, job.description_text_clean))
    return tuple(sections)


def build_evidence(
    *,
    job: CleanedJob,
    candidate: AliasCandidate,
    text: str,
    section_name: str,
    profile: ExtractionProfile,
    dictionary: RequirementDictionary,
    config_hash: str,
    suppressed: bool,
) -> RequirementEvidence:
    """Build one typed accepted or negative-context-suppressed evidence row."""
    section_weight = profile.section_weights[section_name]
    canonical_match = (
        candidate.alias.alias_text.casefold()
        == candidate.alias.requirement_name.casefold()
    )
    multiplier = Decimal("1.0") if canonical_match else Decimal("0.9")
    score = Decimal("0") if suppressed else section_weight * multiplier
    return RequirementEvidence(
        source_code=job.source_code,
        source_job_id=job.source_job_id,
        requirement_code=candidate.alias.requirement_code,
        requirement_name=candidate.alias.requirement_name,
        requirement_type=candidate.alias.requirement_type,
        category_code=candidate.alias.category_code,
        alias_text=candidate.alias.alias_text,
        matched_text=candidate.matched_text,
        section_name=section_name,
        section_weight=section_weight,
        evidence_start=candidate.start,
        evidence_end=candidate.end,
        evidence_snippet=evidence_snippet(
            text,
            candidate.start,
            candidate.end,
            profile.evidence_snippet_length,
            avoid_full_section=section_name == "description_text_clean",
        ),
        match_type=candidate.alias.match_type,
        evidence_score=score.quantize(Decimal("0.0001")),
        dictionary_version=dictionary.dictionary_version,
        dictionary_hash=dictionary.dictionary_hash,
        profile_version=profile.profile_version,
        profile_hash=profile.profile_hash,
        extractor_version=profile.extractor_version,
        extractor_config_hash=config_hash,
        extraction_output_schema_version=profile.extraction_output_schema_version,
        evidence_status=("suppressed_negative_context" if suppressed else "accepted"),
    )


def extract_job_evidence(
    job: CleanedJob,
    profile: ExtractionProfile,
    dictionary: RequirementDictionary,
) -> JobEvidenceResult:
    """Extract all deterministic accepted and suppressed evidence for one job."""
    config_hash = extractor_config_hash(profile)
    evidence: list[tuple[int, int, int, RequirementEvidence]] = []
    suppressed_count = 0

    for section_name, section_position, raw_text in content_sections(job):
        text = normalized_section_text(raw_text)
        accepted_spans: list[tuple[int, int]] = []
        for candidate in alias_candidates(text, dictionary.active_aliases):
            if overlaps_existing(candidate, accepted_spans):
                continue
            accepted_spans.append((candidate.start, candidate.end))
            suppressed = negative_context_found(
                text, candidate, profile.negative_context_window
            )
            suppressed_count += suppressed
            row = build_evidence(
                job=job,
                candidate=candidate,
                text=text,
                section_name=section_name,
                profile=profile,
                dictionary=dictionary,
                config_hash=config_hash,
                suppressed=suppressed,
            )
            evidence.append(
                (
                    SECTION_ORDER[section_name],
                    section_position,
                    candidate.start,
                    row,
                )
            )

    ordered_evidence = tuple(
        row
        for _, _, _, row in sorted(
            evidence,
            key=lambda item: (
                item[0],
                item[1],
                item[2],
                item[3].requirement_code,
                item[3].alias_text.casefold(),
            ),
        )
    )
    return JobEvidenceResult(
        evidence=ordered_evidence,
        suppressed_negative_context_count=suppressed_count,
        extractor_config_hash=config_hash,
    )
