"""Classify jobs for profile relevance using bounded independent evidence.

This reusable classification engine consumes canonical jobs and typed upstream
results. It must not read files, classify role or seniority, or publish jobs to
an analytical population.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from skill_compass.classification.errors import RelevanceReconciliationError
from skill_compass.schemas.classification import (
    JobProfileRelevance,
    JobRoleClassification,
    JobSeniorityClassification,
    ProfileRelevanceDiagnostic,
    ProfileRelevanceEvidence,
    ProfileRelevanceReviewQueueItem,
    ProfileRelevanceRunResult,
    ProfileRelevanceSummary,
    RelevanceRuleSet,
)
from skill_compass.schemas.extraction import JobRequirementMatch
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Stable internal input and normalization helpers
# =============================================================================


SCORE_QUANTUM = Decimal("0.0001")
NORMALIZATION_PATTERN = re.compile(r"[^a-z0-9]+")
RESPONSIBILITY_SECTION_ORDER = (
    "summary_text_clean",
    "bullet_points_clean",
    "description_text_clean",
)
SOURCE_FIELDS = (
    "source_role_code_raw",
    "classification_raw",
    "classification_code_raw",
    "subclassification_raw",
    "subclassification_code_raw",
)


@dataclass(frozen=True, slots=True)
class RelevanceJobInput:
    """Join one job to the exact upstream evidence used by Feature 7."""

    job: CleanedJob
    role: JobRoleClassification
    requirements: tuple[JobRequirementMatch, ...] = ()
    seniority: JobSeniorityClassification | None = None


def _normalize(value: str | None) -> str:
    """Normalize canonical text and configured phrases for boundary matching."""
    return NORMALIZATION_PATTERN.sub(" ", (value or "").casefold()).strip()


def _contains_phrase(text: str | None, term: str) -> bool:
    """Match a full normalized phrase without substring false positives."""
    normalized_text = _normalize(text)
    normalized_term = _normalize(term)
    return bool(
        normalized_text
        and normalized_term
        and f" {normalized_term} " in f" {normalized_text} "
    )


def _equals_phrase(text: str | None, term: str) -> bool:
    """Compare a whole normalized field to a governed phrase."""
    return bool(_normalize(text) and _normalize(text) == _normalize(term))


def _bounded(value: Decimal) -> Decimal:
    """Clamp a stable score to 0-1 and four decimal places."""
    return min(Decimal("1"), max(Decimal("0"), value)).quantize(
        SCORE_QUANTUM, rounding=ROUND_HALF_UP
    )


def _weighted(base: Decimal, multiplier: Decimal = Decimal("1")) -> Decimal:
    """Return a signed evidence contribution at stable precision."""
    return (base * multiplier).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)


def _snippet(text: str | None, term: str, maximum: int) -> str:
    """Return a bounded single-line context window without full descriptions."""
    compact = " ".join((text or "").split())
    if not compact:
        return ""
    position = compact.casefold().find(term.casefold())
    if position < 0:
        return compact[:maximum]
    half = maximum // 2
    start = max(0, position - half)
    end = min(len(compact), start + maximum)
    return compact[start:end]


def _evidence(
    *,
    item: RelevanceJobInput,
    rules: RelevanceRuleSet,
    family: str,
    section: str,
    term: str,
    effect: str,
    weight: Decimal,
    context: str = "",
) -> ProfileRelevanceEvidence:
    """Build one typed, bounded, profile-neutral evidence row."""
    return ProfileRelevanceEvidence.model_validate(
        {
            "source_code": item.job.source_code,
            "source_job_id": item.job.source_job_id,
            "evidence_family": family,
            "evidence_section": section,
            "evidence_term": " ".join(term.split())[
                : rules.limits.evidence_term_max_length
            ],
            "evidence_effect": effect,
            "evidence_weight": weight,
            "context_snippet": _snippet(
                context, term, rules.limits.context_snippet_max_length
            ),
        }
    )


# =============================================================================
# Independent evidence-family collection
# =============================================================================


def _role_evidence(
    item: RelevanceJobInput, rules: RelevanceRuleSet
) -> list[ProfileRelevanceEvidence]:
    """Use Feature 5 as strong but non-absolute relevance evidence."""
    role = item.role
    rows: list[ProfileRelevanceEvidence] = []
    role_code = role.role_group_code
    if role_code in rules.approved_role_codes:
        weight = {
            "high": rules.weights.approved_role_high,
            "medium": rules.weights.approved_role_medium,
            "low": rules.weights.approved_role_low,
        }[role.role_confidence_level]
        rows.append(
            _evidence(
                item=item,
                rules=rules,
                family="role",
                section="feature_5_role",
                term=role_code,
                effect="positive",
                weight=weight,
                context=role.role_reason,
            )
        )
    elif role.role_review_flag:
        candidate = role.candidate_role_1_code
        if candidate in rules.approved_role_codes:
            rows.append(
                _evidence(
                    item=item,
                    rules=rules,
                    family="role",
                    section="feature_5_candidate",
                    term=candidate or "review",
                    effect="positive",
                    weight=rules.weights.approved_role_low,
                    context=role.role_reason,
                )
            )
        rows.append(
            _evidence(
                item=item,
                rules=rules,
                family="role",
                section="feature_5_role",
                term="review",
                effect="conflicting",
                weight=Decimal("0"),
                context=role.role_reason,
            )
        )
    return rows


def _longest_match(text: str | None, terms: tuple[str, ...]) -> str | None:
    """Select one deterministic longest match from a governed term group."""
    matches = [term for term in terms if _contains_phrase(text, term)]
    if not matches:
        return None
    return sorted(
        matches, key=lambda value: (-len(_normalize(value)), _normalize(value))
    )[0]


def _title_evidence(
    item: RelevanceJobInput, rules: RelevanceRuleSet
) -> list[ProfileRelevanceEvidence]:
    """Apply at most one positive, adjacent, and negative title contribution."""
    title = item.job.title_clean
    rows: list[ProfileRelevanceEvidence] = []
    groups = (
        (rules.strongly_included_title_terms, rules.weights.strong_title, "positive"),
        (rules.generally_included_title_terms, rules.weights.general_title, "positive"),
    )
    for terms, weight, effect in groups:
        match = _longest_match(title, terms)
        if match is not None:
            rows.append(
                _evidence(
                    item=item,
                    rules=rules,
                    family="title",
                    section="title_clean",
                    term=match,
                    effect=effect,
                    weight=weight,
                    context=title,
                )
            )
            break
    adjacent = _longest_match(title, rules.adjacent_title_terms)
    if adjacent is not None:
        rows.append(
            _evidence(
                item=item,
                rules=rules,
                family="title",
                section="title_clean",
                term=adjacent,
                effect="conflicting",
                weight=rules.weights.adjacent_title,
                context=title,
            )
        )
    excluded = _longest_match(title, rules.strongly_excluded_title_terms)
    if excluded is not None:
        rows.append(
            _evidence(
                item=item,
                rules=rules,
                family="title",
                section="title_clean",
                term=excluded,
                effect="negative",
                weight=-rules.weights.negative_title,
                context=title,
            )
        )
    return rows


def _responsibility_evidence(
    item: RelevanceJobInput, rules: RelevanceRuleSet
) -> list[ProfileRelevanceEvidence]:
    """Count each configured responsibility once at its strongest section."""
    section_values = {
        "summary_text_clean": item.job.summary_text_clean or "",
        "bullet_points_clean": " ".join(item.job.bullet_points_clean),
        "description_text_clean": item.job.description_text_clean or "",
    }
    rows: list[ProfileRelevanceEvidence] = []
    groups = (
        (
            rules.positive_responsibility_terms,
            rules.weights.positive_responsibility,
            "positive",
            rules.limits.positive_terms_per_section,
        ),
        (
            rules.negative_responsibility_terms,
            rules.weights.negative_responsibility,
            "negative",
            rules.limits.negative_terms_per_section,
        ),
    )
    for terms, base_weight, effect, limit in groups:
        matches: list[tuple[Decimal, str, str]] = []
        for term in terms:
            sections = [
                section
                for section in RESPONSIBILITY_SECTION_ORDER
                if _contains_phrase(section_values[section], term)
            ]
            if not sections:
                continue
            section = sorted(
                sections,
                key=lambda value: (
                    -rules.responsibility_section_multipliers[value],
                    RESPONSIBILITY_SECTION_ORDER.index(value),
                ),
            )[0]
            weight = _weighted(
                base_weight, rules.responsibility_section_multipliers[section]
            )
            if effect == "negative":
                weight = -weight
            matches.append((weight, term, section))
        selected = sorted(
            matches, key=lambda value: (-abs(value[0]), _normalize(value[1]), value[2])
        )[:limit]
        rows.extend(
            _evidence(
                item=item,
                rules=rules,
                family="responsibilities",
                section=section,
                term=term,
                effect=effect,
                weight=weight,
                context=section_values[section],
            )
            for weight, term, section in selected
        )
    return rows


def _source_evidence(
    item: RelevanceJobInput, rules: RelevanceRuleSet
) -> list[ProfileRelevanceEvidence]:
    """Use canonical source taxonomy only as weak bounded context."""
    rows: list[ProfileRelevanceEvidence] = []
    groups = (
        (rules.positive_source_terms, rules.weights.positive_source, "positive"),
        (rules.negative_source_terms, -rules.weights.negative_source, "negative"),
    )
    for terms, weight, effect in groups:
        matches: list[tuple[str, str, str]] = []
        for term in terms:
            for field_name in SOURCE_FIELDS:
                value = getattr(item.job, field_name)
                if value and _contains_phrase(value, term):
                    matches.append((term, field_name, value))
                    break
        selected = sorted(matches, key=lambda value: (_normalize(value[0]), value[1]))[
            : rules.limits.source_terms
        ]
        rows.extend(
            _evidence(
                item=item,
                rules=rules,
                family="source_taxonomy",
                section=field_name,
                term=term,
                effect=effect,
                weight=weight,
                context=value,
            )
            for term, field_name, value in selected
        )
    return rows


def _requirement_evidence(
    item: RelevanceJobInput, rules: RelevanceRuleSet
) -> list[ProfileRelevanceEvidence]:
    """Use distinct extracted requirements as support, never sole proof."""
    candidates: list[tuple[Decimal, JobRequirementMatch]] = []
    for match in item.requirements:
        if match.requirement_code in rules.strong_requirement_codes:
            base = rules.weights.strong_requirement
        elif match.category_code in rules.positive_requirement_categories:
            base = rules.weights.category_requirement
        else:
            continue
        candidates.append((_weighted(base, match.extraction_score), match))
    selected = sorted(
        candidates,
        key=lambda value: (-value[0], value[1].requirement_code),
    )[: rules.limits.requirements_per_group]
    return [
        _evidence(
            item=item,
            rules=rules,
            family="requirements",
            section="feature_3_requirements",
            term=match.requirement_code,
            effect="positive",
            weight=weight,
            context=f"{match.requirement_name}; {match.category_code}",
        )
        for weight, match in selected
    ]


def collect_relevance_evidence(
    item: RelevanceJobInput, rules: RelevanceRuleSet
) -> tuple[ProfileRelevanceEvidence, ...]:
    """Collect all bounded evidence families in deterministic hierarchy order."""
    return tuple(
        [
            *_role_evidence(item, rules),
            *_title_evidence(item, rules),
            *_responsibility_evidence(item, rules),
            *_source_evidence(item, rules),
            *_requirement_evidence(item, rules),
        ]
    )


# =============================================================================
# Three-stage deterministic decision policy
# =============================================================================


def _usable_text_length(job: CleanedJob) -> int:
    """Measure normalized canonical text available across approved sections."""
    sections = (
        job.title_clean,
        job.summary_text_clean or "",
        " ".join(job.bullet_points_clean),
        job.description_text_clean or "",
    )
    return len(" ".join(_normalize(section) for section in sections).strip())


def _strengths(
    evidence: tuple[ProfileRelevanceEvidence, ...], rules: RelevanceRuleSet
) -> tuple[Decimal, Decimal, Decimal, set[str], set[str]]:
    """Calculate bounded positive/negative strength and diversity-adjusted score."""
    positive = sum(
        (row.evidence_weight for row in evidence if row.evidence_weight > 0),
        Decimal("0"),
    )
    negative = sum(
        (-row.evidence_weight for row in evidence if row.evidence_weight < 0),
        Decimal("0"),
    )
    positive_families = {
        row.evidence_family for row in evidence if row.evidence_weight > 0
    }
    negative_families = {
        row.evidence_family for row in evidence if row.evidence_weight < 0
    }
    diversity_count = min(
        max(0, len(positive_families) - 1),
        rules.limits.maximum_diversity_bonus_families,
    )
    positive += rules.weights.evidence_diversity_bonus * diversity_count
    score = _bounded(Decimal("0.5") + (positive - negative) / Decimal("2"))
    return positive, negative, score, positive_families, negative_families


def _decision(
    item: RelevanceJobInput,
    rules: RelevanceRuleSet,
    evidence: tuple[ProfileRelevanceEvidence, ...],
) -> tuple[str, str, str, Decimal, set[str], set[str]]:
    """Apply direct, weighted, then relationship-based fallback resolution."""
    positive, negative, score, positive_families, negative_families = _strengths(
        evidence, rules
    )
    thresholds = rules.thresholds
    title = item.job.title_clean
    adjacent = any(_contains_phrase(title, term) for term in rules.adjacent_title_terms)
    generic = any(_equals_phrase(title, term) for term in rules.generic_title_terms)
    positive_title = any(
        row.evidence_family == "title"
        and row.evidence_section == "title_clean"
        and row.evidence_weight > 0
        and row.evidence_effect == "positive"
        for row in evidence
    )
    negative_title = any(
        row.evidence_family == "title" and row.evidence_weight < 0 for row in evidence
    )
    positive_requirement_count = sum(
        row.evidence_family == "requirements" and row.evidence_weight > 0
        for row in evidence
    )
    negative_responsibility_count = sum(
        row.evidence_family == "responsibilities" and row.evidence_weight < 0
        for row in evidence
    )
    usable_length = _usable_text_length(item.job)
    role_uncertain = item.role.role_review_flag

    # Stage 1 resolves only broad, independent, non-conflicting evidence.
    if (
        positive >= thresholds.direct_positive_strength
        and len(positive_families) >= 3
        and negative < thresholds.meaningful_signal
        and not adjacent
    ):
        return (
            "included",
            "direct_multi_source_inclusion",
            "Strong positive evidence spans at least three independent families.",
            score,
            positive_families,
            negative_families,
        )
    if (
        negative >= thresholds.direct_negative_strength
        and positive < thresholds.meaningful_signal
    ):
        return (
            "excluded",
            "direct_clear_exclusion",
            "Strong unrelated title and context evidence has no meaningful analytics support.",
            score,
            positive_families,
            negative_families,
        )

    # Strong opposed signals of similar size remain Review before score bands.
    if (
        positive >= thresholds.conflict_strength
        and negative >= thresholds.conflict_strength
        and abs(positive - negative) <= thresholds.conflict_margin
    ):
        return (
            "review",
            "positive_negative_tie",
            "Strong positive and negative evidence remain inside the conflict margin.",
            score,
            positive_families,
            negative_families,
        )
    if adjacent:
        return (
            "review",
            "adjacent_role",
            "The governed title is adjacent to, but not decisively inside, this profile.",
            score,
            positive_families,
            negative_families,
        )
    if (positive_title and negative_responsibility_count >= 2) or (
        negative_title and positive_requirement_count >= 2
    ):
        return (
            "review",
            "conflicting_role_evidence",
            "Strong title evidence conflicts with independent context or requirements.",
            score,
            positive_families,
            negative_families,
        )

    # Stage 2 uses governed score bands only when evidence is not contradictory.
    if score >= thresholds.inclusion_score and negative < thresholds.conflict_strength:
        return (
            "included",
            "weighted_inclusion",
            "Bounded contextual evidence exceeds the governed inclusion threshold.",
            score,
            positive_families,
            negative_families,
        )
    if score <= thresholds.exclusion_score and positive < thresholds.conflict_strength:
        return (
            "excluded",
            "weighted_exclusion",
            "Bounded unrelated evidence is below the governed exclusion threshold.",
            score,
            positive_families,
            negative_families,
        )

    # Stage 3 resolves evidence relationships without weakening score thresholds.
    if (
        positive >= thresholds.fallback_positive_strength
        and len(positive_families) >= 3
        and negative < thresholds.meaningful_signal
    ):
        return (
            "included",
            "multi_evidence_inclusion",
            "Three independent evidence families resolve an otherwise marginal score.",
            score,
            positive_families,
            negative_families,
        )
    substantive_positive_families = positive_families & {
        "role",
        "title",
        "responsibilities",
    }
    if (
        item.role.role_group_code == "other"
        and not substantive_positive_families
        and usable_length >= thresholds.minimum_usable_text_length
        and not generic
    ):
        return (
            "excluded",
            "clear_irrelevance",
            "Source taxonomy or requirements alone do not establish profile relevance.",
            score,
            positive_families,
            negative_families,
        )
    if (
        item.role.role_group_code == "other"
        and positive <= thresholds.weak_positive_ceiling
        and usable_length >= thresholds.minimum_usable_text_length
        and not generic
    ):
        return (
            "excluded",
            "clear_irrelevance",
            "Usable context and Feature 5 show no meaningful analytics relevance.",
            score,
            positive_families,
            negative_families,
        )
    if (
        negative > positive + thresholds.meaningful_signal
        and usable_length >= thresholds.minimum_usable_text_length
        and not generic
    ):
        return (
            "excluded",
            "clear_irrelevance",
            "Unrelated contextual evidence clearly outweighs analytics evidence.",
            score,
            positive_families,
            negative_families,
        )
    if generic:
        return (
            "review",
            "generic_analyst_title",
            "A generic title lacks enough independent evidence for a safe decision.",
            score,
            positive_families,
            negative_families,
        )
    if usable_length < thresholds.minimum_usable_text_length and not item.requirements:
        return (
            "review",
            "insufficient_evidence",
            "Total usable canonical evidence is insufficient for a safe decision.",
            score,
            positive_families,
            negative_families,
        )
    if role_uncertain and positive >= thresholds.meaningful_signal:
        return (
            "review",
            "role_classifier_uncertain",
            "Feature 5 remains uncertain and other evidence does not safely resolve it.",
            score,
            positive_families,
            negative_families,
        )
    if (
        positive >= thresholds.meaningful_signal
        and negative >= thresholds.meaningful_signal
    ):
        return (
            "review",
            "conflicting_role_evidence",
            "Positive and unrelated evidence conflict without a governed precedence.",
            score,
            positive_families,
            negative_families,
        )
    return (
        "review",
        "weak_relevance_signal",
        "Available evidence is meaningful but too weak for a safe automated decision.",
        score,
        positive_families,
        negative_families,
    )


def classify_job_relevance(
    item: RelevanceJobInput,
    rules: RelevanceRuleSet,
    *,
    classified_at: datetime,
) -> tuple[JobProfileRelevance, tuple[ProfileRelevanceEvidence, ...]]:
    """Classify one joined job and return its complete bounded evidence."""
    evidence = collect_relevance_evidence(item, rules)
    status, reason_code, reason, score, positive_families, negative_families = (
        _decision(item, rules, evidence)
    )
    quality_flags = tuple(
        flag
        for flag, present in (
            ("missing_title", not item.job.title_clean.strip()),
            ("missing_description", not item.job.description_text_clean),
            ("no_extracted_requirements", not item.requirements),
            ("role_classifier_review", item.role.role_review_flag),
        )
        if present
    )
    result = JobProfileRelevance(
        source_code=item.job.source_code,
        source_job_id=item.job.source_job_id,
        profile_code=rules.profile_code,
        relevance_status=status,
        relevance_score=score,
        relevance_review_flag=status == "review",
        relevance_reason_code=reason_code,
        relevance_reason=reason,
        relevance_classifier_version=rules.relevance_classifier_version,
        relevance_rules_version=rules.relevance_rules_version,
        relevance_rules_hash=rules.relevance_rules_hash,
        positive_evidence_count=sum(row.evidence_weight > 0 for row in evidence),
        negative_evidence_count=sum(row.evidence_weight < 0 for row in evidence),
        evidence_family_count=len(positive_families | negative_families),
        relevance_quality_flags=quality_flags,
        classified_at=classified_at,
    )
    return result, evidence


# =============================================================================
# Run aggregation, review queue, and cross-feature diagnostics
# =============================================================================


def _review_item(
    item: RelevanceJobInput,
    result: JobProfileRelevance,
    evidence: tuple[ProfileRelevanceEvidence, ...],
    rules: RelevanceRuleSet,
) -> ProfileRelevanceReviewQueueItem:
    """Build one privacy-safe manual-review row with bounded evidence."""
    compact = "; ".join(
        f"{row.evidence_family}:{row.evidence_section}:{row.evidence_term}"
        for row in evidence
    )
    return ProfileRelevanceReviewQueueItem(
        source_code=item.job.source_code,
        source_job_id=item.job.source_job_id,
        title_clean=" ".join(item.job.title_clean.split())[:160],
        relevance_score=result.relevance_score,
        relevance_reason_code=result.relevance_reason_code,
        relevance_reason=result.relevance_reason,
        bounded_evidence=compact[: rules.limits.review_evidence_max_length],
    )


def _diagnostic(
    item: RelevanceJobInput, result: JobProfileRelevance
) -> ProfileRelevanceDiagnostic:
    """Create a diagnostic row; seniority is reported but never scored."""
    seniority = item.seniority
    return ProfileRelevanceDiagnostic(
        source_code=item.job.source_code,
        source_job_id=item.job.source_job_id,
        relevance_status=result.relevance_status,
        relevance_score=result.relevance_score,
        role_group=item.role.role_group_code,
        role_confidence=item.role.role_confidence_score,
        seniority_level=seniority.seniority_code if seniority else None,
        seniority_confidence=(
            seniority.seniority_confidence_score if seniority else None
        ),
        requirement_count=len(item.requirements),
        usable_text_length=_usable_text_length(item.job),
        missing_title=not item.job.title_clean.strip(),
        description_available=bool(item.job.description_text_clean),
        review_reason=result.relevance_reason if result.relevance_review_flag else None,
    )


def classify_profile_relevance(
    inputs: tuple[RelevanceJobInput, ...],
    rules: RelevanceRuleSet,
    *,
    classified_at: datetime,
) -> ProfileRelevanceRunResult:
    """Classify a complete joined input and build reconciled Feature 7 outputs."""
    classifications: list[JobProfileRelevance] = []
    evidence_rows: list[ProfileRelevanceEvidence] = []
    review_rows: list[ProfileRelevanceReviewQueueItem] = []
    diagnostics: list[ProfileRelevanceDiagnostic] = []
    for item in inputs:
        result, evidence = classify_job_relevance(
            item, rules, classified_at=classified_at
        )
        classifications.append(result)
        evidence_rows.extend(evidence)
        diagnostics.append(_diagnostic(item, result))
        if result.relevance_review_flag:
            review_rows.append(_review_item(item, result, evidence, rules))

    counts = Counter(row.relevance_status for row in classifications)
    reasons = Counter(row.relevance_reason_code for row in classifications)
    role_supported_keys = {
        (row.source_code, row.source_job_id)
        for row in evidence_rows
        if row.evidence_family == "role" and row.evidence_weight > 0
    }
    denominator = len(inputs)

    def rate(count: int) -> Decimal:
        return (
            _bounded(Decimal(count) / Decimal(denominator))
            if denominator
            else Decimal("0")
        )

    summary = ProfileRelevanceSummary(
        total_classifier_input=denominator,
        included_count=counts["included"],
        included_rate=rate(counts["included"]),
        excluded_count=counts["excluded"],
        excluded_rate=rate(counts["excluded"]),
        review_count=counts["review"],
        review_rate=rate(counts["review"]),
        missing_description_count=sum(
            not item.job.description_text_clean for item in inputs
        ),
        insufficient_evidence_count=reasons["insufficient_evidence"],
        conflicting_evidence_count=sum(
            reasons[code]
            for code in (
                "conflicting_role_evidence",
                "positive_negative_tie",
                "role_classifier_uncertain",
            )
        ),
        role_supported_decision_count=sum(
            (result.source_code, result.source_job_id) in role_supported_keys
            and not result.relevance_review_flag
            for result in classifications
        ),
        multi_evidence_decision_count=sum(
            result.evidence_family_count >= 3 and not result.relevance_review_flag
            for result in classifications
        ),
        reconciliation_status=(
            "pass" if sum(counts.values()) == denominator else "fail"
        ),
        denominator_definition=(
            "All joined canonical jobs; Included, Excluded, and Review are separate."
        ),
    )
    reconciliation_passed = (
        len(classifications) == denominator
        and sum(counts.values()) == denominator
        and len(review_rows) == counts["review"]
        and len(diagnostics) == denominator
        and summary.reconciliation_status == "pass"
    )
    if not reconciliation_passed:
        raise RelevanceReconciliationError(
            "profile relevance decisions, reviews, or diagnostics did not reconcile"
        )
    return ProfileRelevanceRunResult(
        rules=rules,
        input_job_count=denominator,
        classifications=tuple(classifications),
        evidence=tuple(evidence_rows),
        summary=summary,
        review_queue=tuple(review_rows),
        diagnostics=tuple(diagnostics),
        reconciliation_passed=True,
    )
