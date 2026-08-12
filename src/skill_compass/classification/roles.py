"""Classify cleaned jobs into governed role groups with bounded evidence.

This classification engine consumes only typed canonical jobs and declarative
rules; it must not read files, classify seniority, decide profile relevance,
or know source-specific actor field paths.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from skill_compass.classification.config import APPROVED_OUTCOME_LABELS
from skill_compass.classification.errors import RoleReconciliationError
from skill_compass.schemas.classification import (
    JobRoleClassification,
    RoleClassificationEvidence,
    RoleClassificationQuality,
    RoleClassificationRunResult,
    RoleDistributionSummary,
    RoleReviewQueueItem,
    RoleRule,
    RoleRuleSet,
)
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Deterministic text and score helpers
# =============================================================================


SCORE_QUANTUM = Decimal("0.0001")
CONTEXT_SECTION_ORDER = (
    "summary_text_clean",
    "bullet_points_clean",
    "description_text_clean",
)
SOURCE_HINT_FIELDS = (
    "source_role_code_raw",
    "classification_raw",
    "classification_code_raw",
    "subclassification_raw",
    "subclassification_code_raw",
)
NORMALIZATION_PATTERN = re.compile(r"[^a-z0-9]+")


def _normalize(value: str | None) -> str:
    """Normalize configured phrases and canonical evidence for boundary matching."""
    return NORMALIZATION_PATTERN.sub(" ", (value or "").casefold()).strip()


def _contains_phrase(text: str, term: str) -> bool:
    """Match a complete normalized phrase without substring false positives."""
    normalized_text = _normalize(text)
    normalized_term = _normalize(term)
    if not normalized_text or not normalized_term:
        return False
    return f" {normalized_term} " in f" {normalized_text} "


def _bounded_score(value: Decimal) -> Decimal:
    """Clamp a deterministic strength score to 0-1 and four decimal places."""
    return min(Decimal("1"), max(Decimal("0"), value)).quantize(
        SCORE_QUANTUM, rounding=ROUND_HALF_UP
    )


def _weighted_value(base: Decimal, multiplier: Decimal = Decimal("1")) -> Decimal:
    """Return one signed evidence contribution at stable output precision."""
    return (base * multiplier).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)


def _longest_match(text: str, terms: tuple[str, ...]) -> str | None:
    """Choose one deterministic longest matching term from an evidence group."""
    matches = [term for term in terms if _contains_phrase(text, term)]
    if not matches:
        return None
    return sorted(matches, key=lambda term: (-len(_normalize(term)), _normalize(term)))[
        0
    ]


# =============================================================================
# Candidate evidence collection and scoring
# =============================================================================


@dataclass(frozen=True, slots=True)
class _RoleCandidate:
    """Keep one internal candidate score and the evidence producing it."""

    rule: RoleRule
    score: Decimal
    positive_score: Decimal
    has_context_evidence: bool
    evidence: tuple[RoleClassificationEvidence, ...]


def _evidence(
    *,
    job: CleanedJob,
    rule: RoleRule,
    section: str,
    term: str,
    evidence_type: str,
    weight: Decimal,
    effect: str,
    max_length: int,
) -> RoleClassificationEvidence:
    """Build one bounded typed evidence row from a configured matched term."""
    return RoleClassificationEvidence.model_validate(
        {
            "source_code": job.source_code,
            "source_job_id": job.source_job_id,
            "role_group_code": rule.role_group_code,
            "evidence_section": section,
            "evidence_term": " ".join(term.split())[:max_length],
            "evidence_type": evidence_type,
            "evidence_weight": weight,
            "evidence_effect": effect,
        }
    )


def _title_evidence(
    job: CleanedJob, rule: RoleRule, rules: RoleRuleSet
) -> list[RoleClassificationEvidence]:
    """Apply at most one positive and two negative bounded title contributions."""
    rows: list[RoleClassificationEvidence] = []
    strong_match = _longest_match(job.title_clean, rule.strong_title_terms)
    supporting_match = None
    if strong_match is None:
        supporting_match = _longest_match(job.title_clean, rule.supporting_title_terms)
    if strong_match is not None:
        rows.append(
            _evidence(
                job=job,
                rule=rule,
                section="title_clean",
                term=strong_match,
                evidence_type="strong_title",
                weight=rules.weights.strong_title,
                effect="positive",
                max_length=rules.evidence_term_max_length,
            )
        )
    elif supporting_match is not None:
        rows.append(
            _evidence(
                job=job,
                rule=rule,
                section="title_clean",
                term=supporting_match,
                evidence_type="supporting_title",
                weight=rules.weights.supporting_title,
                effect="supporting",
                max_length=rules.evidence_term_max_length,
            )
        )

    conflicting_match = _longest_match(job.title_clean, rule.conflicting_title_terms)
    if conflicting_match is not None:
        rows.append(
            _evidence(
                job=job,
                rule=rule,
                section="title_clean",
                term=conflicting_match,
                evidence_type="conflicting_title",
                weight=-rules.weights.conflicting_title,
                effect="conflicting",
                max_length=rules.evidence_term_max_length,
            )
        )
    exclusion_match = _longest_match(job.title_clean, rule.exclusion_title_terms)
    if exclusion_match is not None:
        rows.append(
            _evidence(
                job=job,
                rule=rule,
                section="title_clean",
                term=exclusion_match,
                evidence_type="exclusion_title",
                weight=-rules.weights.exclusion_title,
                effect="conflicting",
                max_length=rules.evidence_term_max_length,
            )
        )
    return rows


def _context_evidence(
    job: CleanedJob, rule: RoleRule, rules: RoleRuleSet
) -> list[RoleClassificationEvidence]:
    """Count each distinct context term once at its strongest matching section."""
    section_values = {
        "summary_text_clean": job.summary_text_clean or "",
        "bullet_points_clean": " ".join(job.bullet_points_clean),
        "description_text_clean": job.description_text_clean or "",
    }
    matches: list[tuple[Decimal, str, str]] = []
    for term in rule.context_terms:
        matching_sections = [
            section
            for section in CONTEXT_SECTION_ORDER
            if _contains_phrase(section_values[section], term)
        ]
        if not matching_sections:
            continue
        section = sorted(
            matching_sections,
            key=lambda name: (
                -rules.section_multipliers[name],
                CONTEXT_SECTION_ORDER.index(name),
            ),
        )[0]
        weight = _weighted_value(
            rules.weights.context_term, rules.section_multipliers[section]
        )
        matches.append((weight, term, section))

    selected = sorted(
        matches, key=lambda item: (-item[0], _normalize(item[1]), item[2])
    )[: rules.max_context_terms_per_role]
    return [
        _evidence(
            job=job,
            rule=rule,
            section=section,
            term=term,
            evidence_type="context_term",
            weight=weight,
            effect="supporting",
            max_length=rules.evidence_term_max_length,
        )
        for weight, term, section in selected
    ]


def _source_hint_evidence(
    job: CleanedJob, rule: RoleRule, rules: RoleRuleSet
) -> list[RoleClassificationEvidence]:
    """Use canonical source-category hints as weak, bounded supporting evidence."""
    matched: list[tuple[str, str]] = []
    for term in rule.source_hint_terms:
        for field_name in SOURCE_HINT_FIELDS:
            value = getattr(job, field_name)
            if value and _contains_phrase(value, term):
                matched.append((term, field_name))
                break
    selected = sorted(matched, key=lambda item: (_normalize(item[0]), item[1]))[
        : rules.max_source_hints_per_role
    ]
    return [
        _evidence(
            job=job,
            rule=rule,
            section=field_name,
            term=term,
            evidence_type="source_hint",
            weight=rules.weights.source_hint,
            effect="supporting",
            max_length=rules.evidence_term_max_length,
        )
        for term, field_name in selected
    ]


def _score_candidate(
    job: CleanedJob, rule: RoleRule, rules: RoleRuleSet
) -> _RoleCandidate:
    """Evaluate one governed role using distinct title, context, and source evidence."""
    evidence = [
        *_title_evidence(job, rule, rules),
        *_context_evidence(job, rule, rules),
        *_source_hint_evidence(job, rule, rules),
    ]
    positive_score = sum(
        (row.evidence_weight for row in evidence if row.evidence_weight > 0),
        Decimal("0"),
    )
    score = _bounded_score(sum((row.evidence_weight for row in evidence), Decimal("0")))
    return _RoleCandidate(
        rule=rule,
        score=score,
        positive_score=_bounded_score(positive_score),
        has_context_evidence=any(
            row.evidence_type == "context_term" for row in evidence
        ),
        evidence=tuple(evidence),
    )


# =============================================================================
# Final decision and run aggregation
# =============================================================================


def _confidence_level(score: Decimal, rules: RoleRuleSet) -> str:
    """Convert a deterministic strength score into a governed display band."""
    if score >= rules.thresholds.high_confidence_min:
        return "high"
    if score >= rules.thresholds.medium_confidence_min:
        return "medium"
    return "low"


def classify_job_role(
    job: CleanedJob, rules: RoleRuleSet
) -> tuple[JobRoleClassification, tuple[RoleClassificationEvidence, ...]]:
    """Classify one cleaned job and return only relevant candidate evidence."""
    candidates = sorted(
        (_score_candidate(job, role, rules) for role in rules.roles),
        key=lambda candidate: (-candidate.score, candidate.rule.sort_order),
    )
    top, second = candidates[:2]
    meaningful = top.positive_score >= rules.thresholds.meaningful_evidence_score
    close_competitor = (
        second.positive_score >= rules.thresholds.meaningful_evidence_score
        and top.score - second.score <= rules.thresholds.ambiguity_margin
    )

    if not meaningful:
        final_code = "other"
        final_label = APPROVED_OUTCOME_LABELS[final_code]
        review_flag = False
        reason = "No approved role has meaningful positive evidence."
    elif close_competitor:
        final_code = "review"
        final_label = APPROVED_OUTCOME_LABELS[final_code]
        review_flag = True
        reason = "Leading role candidates are inside the ambiguity margin."
    elif not top.has_context_evidence:
        final_code = "review"
        final_label = APPROVED_OUTCOME_LABELS[final_code]
        review_flag = True
        reason = "Strong role evidence lacks non-title job-ad context."
    elif top.score < rules.thresholds.minimum_classification_score:
        final_code = "review"
        final_label = APPROVED_OUTCOME_LABELS[final_code]
        review_flag = True
        reason = "Meaningful role evidence is below the classification threshold."
    else:
        final_code = top.rule.role_group_code
        final_label = top.rule.role_group_label
        review_flag = False
        reason = "Clear role winner exceeds the threshold with contextual evidence."

    first_code = top.rule.role_group_code if meaningful else None
    first_score = top.score if meaningful else None
    second_meaningful = (
        second.positive_score >= rules.thresholds.meaningful_evidence_score
    )
    second_code = second.rule.role_group_code if second_meaningful else None
    second_score = second.score if second_meaningful else None
    relevant_codes = {code for code in (first_code, second_code) if code is not None}
    relevant_evidence = tuple(
        row
        for candidate in candidates
        if candidate.rule.role_group_code in relevant_codes
        for row in candidate.evidence
    )
    result = JobRoleClassification(
        source_code=job.source_code,
        source_job_id=job.source_job_id,
        role_group_code=final_code,
        role_group_label=final_label,
        role_confidence_score=top.score,
        role_confidence_level=_confidence_level(top.score, rules),
        role_review_flag=review_flag,
        role_reason=reason,
        candidate_role_1_code=first_code,
        candidate_role_1_score=first_score,
        candidate_role_2_code=second_code,
        candidate_role_2_score=second_score,
        role_classifier_version=rules.role_classifier_version,
        role_rules_version=rules.role_rules_version,
        role_rules_hash=rules.role_rules_hash,
    )
    return result, relevant_evidence


def _build_review_item(
    job: CleanedJob,
    result: JobRoleClassification,
    evidence: tuple[RoleClassificationEvidence, ...],
    rules: RoleRuleSet,
) -> RoleReviewQueueItem:
    """Create one privacy-safe review row with configured bounded evidence."""
    compact = "; ".join(
        f"{row.role_group_code}:{row.evidence_section}:{row.evidence_term}"
        for row in evidence
    )
    return RoleReviewQueueItem(
        source_code=job.source_code,
        source_job_id=job.source_job_id,
        title_clean=" ".join(job.title_clean.split())[:160],
        candidate_role_1_code=result.candidate_role_1_code,
        candidate_role_1_score=result.candidate_role_1_score,
        candidate_role_2_code=result.candidate_role_2_code,
        candidate_role_2_score=result.candidate_role_2_score,
        role_reason=result.role_reason,
        bounded_evidence=compact[: rules.review_evidence_max_length],
    )


def classify_roles(
    jobs: tuple[CleanedJob, ...], rules: RoleRuleSet
) -> RoleClassificationRunResult:
    """Classify all received cleaned jobs and build reconciled tabular outputs."""
    classifications: list[JobRoleClassification] = []
    evidence_rows: list[RoleClassificationEvidence] = []
    review_rows: list[RoleReviewQueueItem] = []
    for job in jobs:
        result, evidence = classify_job_role(job, rules)
        classifications.append(result)
        evidence_rows.extend(evidence)
        if result.role_review_flag:
            review_rows.append(_build_review_item(job, result, evidence, rules))

    counts = Counter(row.role_group_code for row in classifications)
    labels = {role.role_group_code: role.role_group_label for role in rules.roles}
    labels.update(APPROVED_OUTCOME_LABELS)
    ordered_codes = [role.role_group_code for role in rules.roles] + ["other", "review"]
    denominator = len(jobs)
    distribution = tuple(
        RoleDistributionSummary(
            role_group_code=code,
            role_group_label=labels[code],
            job_count=counts[code],
            job_share=(
                _bounded_score(Decimal(counts[code]) / Decimal(denominator))
                if denominator
                else Decimal("0")
            ),
        )
        for code in ordered_codes
    )
    analytical_count = sum(counts[code] for code in ordered_codes[:5])
    review_count = counts["review"]
    confidence_counts = Counter(row.role_confidence_level for row in classifications)
    quality = RoleClassificationQuality(
        total_jobs_received=denominator,
        classified_into_dashboard_role=analytical_count,
        analytical_role_population=analytical_count,
        other_count=counts["other"],
        review_count=review_count,
        review_rate=(
            _bounded_score(Decimal(review_count) / Decimal(denominator))
            if denominator
            else Decimal("0")
        ),
        high_confidence_count=confidence_counts["high"],
        medium_confidence_count=confidence_counts["medium"],
        low_confidence_count=confidence_counts["low"],
        missing_title_count=sum(not job.title_clean.strip() for job in jobs),
        missing_description_count=sum(not job.description_text_clean for job in jobs),
        reconciliation_status=(
            "pass" if sum(counts.values()) == denominator else "fail"
        ),
        denominator_definition=(
            "All cleaned jobs received; dashboard roles, Other, and Review included."
        ),
    )
    reconciliation_passed = (
        len(classifications) == denominator
        and sum(row.job_count for row in distribution) == denominator
        and len(review_rows) == review_count
        and quality.reconciliation_status == "pass"
    )
    if not reconciliation_passed:
        raise RoleReconciliationError(
            "role classifications, distribution, or review queue did not reconcile"
        )
    return RoleClassificationRunResult(
        rules=rules,
        input_job_count=denominator,
        classifications=tuple(classifications),
        evidence=tuple(evidence_rows),
        distribution=distribution,
        quality=quality,
        review_queue=tuple(review_rows),
        reconciliation_passed=True,
    )
