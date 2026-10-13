"""Narrow deterministic protection for generated advisor explanations."""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.orchestration.facts import (
    AdvisorAcademicFacts,
    AdvisorDegreeAuditFacts,
    AdvisorEligibilityFacts,
    AdvisorGroundingAssessment,
    AdvisorPlanningCitation,
)

_SOURCE_RE = re.compile(
    r"\b(?:SRC|REG|DOC|BYLAW|RULE|AUDIT)[_-][A-Za-z0-9_.:/-]+\b",
    re.IGNORECASE,
)
_PAGE_RE = re.compile(r"\b(?:page|p\.)\s*(\d+)\b", re.IGNORECASE)
_ELIGIBILITY_REVIEW_CLAIM_RE = re.compile(
    r"\b(?:registration\s+)?eligibility\b.{0,80}"
    r"\b(?:requires|needs|needed)\b.{0,30}"
    r"\b(?:human|manual|advisor)\s+review\b",
    re.IGNORECASE,
)

_NEGATIVE_ELIGIBILITY = (
    "not eligible",
    "cannot take",
    "can't take",
    "may not take",
    "not allowed",
    "not permitted",
    "ineligible",
    "غير مؤهل",
    "غير مسموح",
    "لا يمكنك تسجيل",
)
_POSITIVE_ELIGIBILITY = (
    "eligible to take",
    "can take",
    "may take",
    "allowed to take",
    "permitted to take",
    "مؤهل للتسجيل",
    "يمكنك تسجيل",
    "مسموح لك",
)
_AUTHORITATIVE_CLAIMS = (
    "officially approved",
    "officially confirmed",
    "authoritative",
    "definitive",
    "guaranteed",
    "معتمد نهائيا",
    "مؤكد رسميا",
)
_NO_PREREQUISITE_CLAIMS = (
    "no prerequisites",
    "has no prerequisites",
    "without prerequisites",
    "لا توجد متطلبات سابقة",
)
_NO_COREQUISITE_CLAIMS = (
    "no corequisites",
    "has no corequisites",
    "without corequisites",
    "لا توجد متطلبات متزامنة",
)


def protect_advisor_text(
    text: str,
    facts: AdvisorAcademicFacts,
) -> tuple[str, AdvisorGroundingAssessment]:
    """Return generated text unless a narrow deterministic contradiction exists.

    This is intentionally not a semantic fact checker.  It checks only stable
    decision, numeric, coverage, authority, and explicit citation patterns
    that can be compared directly with trusted tool projections.
    """

    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    if not isinstance(facts, AdvisorAcademicFacts):
        raise TypeError("facts must be AdvisorAcademicFacts")

    if not _has_trusted_facts(facts):
        return text, AdvisorGroundingAssessment(status="NO_TRUSTED_FACTS")

    issues: list[str] = []
    for fact in facts.eligibility:
        issues.extend(_eligibility_issues(fact, text))
    for fact in facts.degree_audit:
        issues.extend(_degree_audit_issues(fact, text))
    issues.extend(_course_numeric_issues(facts, text))
    issues.extend(_course_coverage_issues(facts, text))
    issues.extend(_authority_issues(facts, text))
    issues.extend(_review_attribution_issues(facts, text))
    issues.extend(_citation_issues(facts, text))
    issues = list(dict.fromkeys(issues))

    if not issues:
        return text, AdvisorGroundingAssessment(status="GROUNDED")
    return (
        _safe_facts_summary(facts),
        AdvisorGroundingAssessment(status="SAFE_FALLBACK", issues=issues),
    )


def _has_trusted_facts(facts: AdvisorAcademicFacts) -> bool:
    return bool(
        facts.eligibility
        or facts.course_information
        or facts.degree_audit
        or facts.official_documents
    )


def _eligibility_issues(
    fact: AdvisorEligibilityFacts,
    text: str,
) -> list[str]:
    lowered = text.casefold()
    if fact.eligible is True and _contains_any(lowered, _NEGATIVE_ELIGIBILITY):
        return ["ELIGIBILITY_CONTRADICTION"]
    if fact.eligible is False and _contains_any(lowered, _POSITIVE_ELIGIBILITY):
        return ["ELIGIBILITY_CONTRADICTION"]
    if fact.eligible is None and _contains_any(
        lowered,
        (*_POSITIVE_ELIGIBILITY, *_NEGATIVE_ELIGIBILITY),
    ):
        return ["INDETERMINATE_ELIGIBILITY_PRESENTED_AS_DEFINITE"]
    return []


def _degree_audit_issues(
    fact: AdvisorDegreeAuditFacts,
    text: str,
) -> list[str]:
    issues: list[str] = []
    labels = {
        "completed": ("completed credits", "credits completed", "earned credits"),
        "required": ("required credits", "credits required"),
        "remaining": ("remaining credits", "credits remaining"),
    }
    lowered = text.casefold()
    for field_name, field_labels in labels.items():
        expected = fact.credits.get(field_name)
        if not isinstance(expected, (int, float)) or isinstance(expected, bool):
            continue
        for label in field_labels:
            match = re.search(
                rf"\b{re.escape(label)}\s*(?:are|is|:|=)?\s*(\d+(?:\.\d+)?)",
                lowered,
            )
            if match is not None and float(match.group(1)) != float(expected):
                issues.append("DEGREE_AUDIT_NUMERIC_CONTRADICTION")

    satisfied = fact.requirements.satisfied_count
    total = fact.requirements.total_count
    summary_match = re.search(
        r"\b(\d+)\s+of\s+(\d+)\s+(?:known\s+)?requirements?\b",
        lowered,
    )
    if summary_match and (
        int(summary_match.group(1)) != satisfied
        or int(summary_match.group(2)) != total
    ):
        issues.append("DEGREE_AUDIT_REQUIREMENT_COUNT_CONTRADICTION")

    if (
        fact.requires_human_review
        and fact.status in {"HUMAN_REVIEW_REQUIRED", "INDETERMINATE"}
        and any(claim in lowered for claim in ("completed all requirements", "ready to graduate"))
    ):
        issues.append("DEGREE_AUDIT_STATUS_CONTRADICTION")
    return issues


def _course_coverage_issues(
    facts: AdvisorAcademicFacts,
    text: str,
) -> list[str]:
    lowered = text.casefold()
    issues: list[str] = []
    for fact in facts.course_information:
        prerequisite_status = fact.coverage.get("prerequisites")
        corequisite_status = fact.coverage.get("corequisites")
        prerequisite_payload = fact.prerequisites
        if (
            prerequisite_status == "COMPLETE"
            and (prerequisite_payload.get("rules") or prerequisite_payload.get("expression"))
            and _contains_any(lowered, _NO_PREREQUISITE_CLAIMS)
        ):
            issues.append("PREREQUISITE_DEFINITION_CONTRADICTION")
        if prerequisite_status != "COMPLETE" and _contains_any(
            lowered, _NO_PREREQUISITE_CLAIMS
        ):
            issues.append("UNAVAILABLE_PREREQUISITES_PRESENTED_AS_ABSENT")
        if corequisite_status != "AVAILABLE" and _contains_any(
            lowered, _NO_COREQUISITE_CLAIMS
        ):
            issues.append("UNAVAILABLE_COREQUISITES_PRESENTED_AS_ABSENT")

    if not facts.course_information and any(
        document.coverage_status != "AVAILABLE"
        and _contains_any(lowered, _NO_PREREQUISITE_CLAIMS)
        for document in facts.official_documents
    ):
        issues.append("NO_RAG_EVIDENCE_PRESENTED_AS_STRUCTURED_FACT")
    return issues


def _course_numeric_issues(
    facts: AdvisorAcademicFacts,
    text: str,
) -> list[str]:
    issues: list[str] = []
    for fact in facts.course_information:
        expected = fact.course.get("credit_hours")
        if not isinstance(expected, (int, float)) or isinstance(expected, bool):
            continue
        match = re.search(
            r"(?:\b(?:credit\s+hours?|course\s+credits?)\s*(?:are|is|:|=)?\s*"
            r"(\d+(?:\.\d+)?)|\b(\d+(?:\.\d+)?)\s+"
            r"(?:credit\s+hours?|course\s+credits?)\b)",
            text,
            re.IGNORECASE,
        )
        actual = (
            next((group for group in match.groups() if group is not None), None)
            if match is not None
            else None
        )
        if actual is not None and float(actual) != float(expected):
            issues.append("COURSE_CREDIT_HOURS_CONTRADICTION")
    return issues


def _authority_issues(facts: AdvisorAcademicFacts, text: str) -> list[str]:
    lowered = text.casefold()
    if not _contains_any(lowered, _AUTHORITATIVE_CLAIMS):
        return []
    if any(not fact.authoritative for fact in facts.eligibility):
        return ["NON_AUTHORITATIVE_ELIGIBILITY_PRESENTED_AS_APPROVED"]
    if any(not fact.authoritative for fact in facts.course_information):
        return ["NON_AUTHORITATIVE_COURSE_FACTS_PRESENTED_AS_APPROVED"]
    if any(not fact.authoritative for fact in facts.degree_audit):
        return ["NON_AUTHORITATIVE_AUDIT_PRESENTED_AS_APPROVED"]
    return []


def _review_attribution_issues(
    facts: AdvisorAcademicFacts,
    text: str,
) -> list[str]:
    if not _ELIGIBILITY_REVIEW_CLAIM_RE.search(text):
        return []
    if any(not fact.requires_human_review for fact in facts.eligibility):
        return ["ELIGIBILITY_REVIEW_FLAG_MISATTRIBUTED"]
    return []


def _citation_issues(facts: AdvisorAcademicFacts, text: str) -> list[str]:
    """Check explicit source/page pairs against returned metadata only.

    This validates metadata consistency, not whether quoted prose semantically
    supports a claim.
    """

    source_pages = _trusted_source_pages(facts)
    issues: list[str] = []
    source_matches = list(_SOURCE_RE.finditer(text))
    known_sources = set(source_pages)
    for source in known_sources:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(source)}(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )
        source_matches.extend(pattern.finditer(text))
    seen_mentions: set[tuple[int, int, str]] = set()
    for source_match in source_matches:
        source = _normalize_source(source_match.group(0))
        mention_key = (source_match.start(), source_match.end(), source)
        if mention_key in seen_mentions:
            continue
        seen_mentions.add(mention_key)
        if source not in source_pages:
            issues.append("UNSUPPORTED_CITATION")
            continue
        sentence = _sentence_containing(text, source_match.start())
        pages = {int(match.group(1)) for match in _PAGE_RE.finditer(sentence)}
        if pages and not any(page in source_pages[source] for page in pages):
            issues.append("CITATION_PAGE_MISMATCH")
    issues.extend(_requirement_citation_issues(facts, text))
    if not source_pages and (_SOURCE_RE.search(text) or _PAGE_RE.search(text)):
        issues.append("CITATION_WITHOUT_TRUSTED_METADATA")
    return issues


def _requirement_citation_issues(
    facts: AdvisorAcademicFacts,
    text: str,
) -> list[str]:
    issues: list[str] = []
    for audit in facts.degree_audit:
        for detail in audit.requirements.details:
            requirement_id = detail.id.casefold()
            start = 0
            while True:
                position = text.casefold().find(requirement_id, start)
                if position == -1:
                    break
                sentence = _sentence_containing(text, position)
                sources = {
                    _normalize_source(match.group(0))
                    for match in _SOURCE_RE.finditer(sentence)
                }
                pages = {
                    int(match.group(1)) for match in _PAGE_RE.finditer(sentence)
                }
                expected = {
                    (citation.source_id.casefold(), citation.page)
                    for citation in detail.provenance
                    if citation.source_id is not None and isinstance(citation.page, int)
                }
                if sources and pages and not any(
                    (source, page) in expected for source in sources for page in pages
                ):
                    issues.append("CITATION_REQUIREMENT_MAPPING")
                start = position + len(requirement_id)
    return issues


def _trusted_source_pages(facts: AdvisorAcademicFacts) -> dict[str, set[int]]:
    values: dict[str, set[int]] = {}
    citations: list[AdvisorPlanningCitation] = []
    for fact in facts.eligibility:
        citations.extend(fact.citations)
    for fact in facts.course_information:
        citations.extend(fact.course_provenance)
        citations.extend(_planning_citations(fact.prerequisites.get("provenance")))
        for rule in fact.prerequisites.get("rules", []):
            if isinstance(rule, dict):
                citations.extend(_planning_citations([rule.get("provenance")]))
    for fact in facts.degree_audit:
        citations.extend(fact.citations)
        for detail in fact.requirements.details:
            citations.extend(detail.provenance)
    for citation in citations:
        if citation.source_id is None or citation.page is None:
            continue
        if isinstance(citation.page, int):
            values.setdefault(citation.source_id.casefold(), set()).add(citation.page)
    for fact in facts.official_documents:
        for evidence in fact.results:
            pages = values.setdefault(evidence.source_id.casefold(), set())
            if evidence.page_start is not None:
                end = evidence.page_end or evidence.page_start
                pages.update(range(evidence.page_start, end + 1))
    return values


def _planning_citations(value: object) -> list[AdvisorPlanningCitation]:
    if not isinstance(value, list):
        return []
    values: list[AdvisorPlanningCitation] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            values.append(AdvisorPlanningCitation.model_validate(item))
        except (TypeError, ValueError):
            continue
    return values


def _safe_facts_summary(facts: AdvisorAcademicFacts) -> str:
    lines = [
        "The generated explanation conflicted with trusted academic facts. "
        "Only the trusted results are shown:",
    ]
    for fact in facts.eligibility:
        course_code = fact.course.get("code", "the requested course")
        lines.append(
            f"Eligibility for {course_code}: {fact.decision} "
            f"(authoritative={str(fact.authoritative).lower()}, "
            f"requires_human_review={str(fact.requires_human_review).lower()})."
        )
    for fact in facts.course_information:
        course_code = fact.course.get("code", "the requested course")
        lines.append(
            f"Course information for {course_code}: prerequisite coverage="
            f"{fact.coverage.get('prerequisites', 'UNKNOWN')}; corequisite coverage="
            f"{fact.coverage.get('corequisites', 'UNKNOWN')}."
        )
    for fact in facts.degree_audit:
        lines.append(
            f"Degree-audit status: {fact.status}; completed credits="
            f"{fact.credits.get('completed')}; remaining credits="
            f"{fact.credits.get('remaining')}; requires_human_review="
            f"{str(fact.requires_human_review).lower()}."
        )
    for fact in facts.official_documents:
        lines.append(
            "Official document evidence is "
            + ("available in the structured evidence field." if fact.evidence_available else "not available.")
        )
    return " ".join(lines)


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    return any(phrase.casefold() in text for phrase in phrases)


def _normalize_source(source: str) -> str:
    return source.rstrip(".,;:)]}").casefold()


def _sentence_containing(text: str, position: int) -> str:
    start = max(
        text.rfind(".", 0, position),
        text.rfind("!", 0, position),
        text.rfind("?", 0, position),
        text.rfind(";", 0, position),
        text.rfind("\n", 0, position),
    )
    ends = [
        index
        for separator in (".", "!", "?", ";", "\n")
        for index in [text.find(separator, position)]
        if index != -1
    ]
    end = min(ends, default=len(text))
    return text[start + 1 : end]


__all__ = ["protect_advisor_text"]
