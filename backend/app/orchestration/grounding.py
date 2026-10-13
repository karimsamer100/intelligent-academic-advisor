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
    r"\b(?:require|requires|need|needs|needed)\b.{0,30}"
    r"\b(?:human|manual|advisor)\s+review\b",
    re.IGNORECASE,
)
_ARABIC_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]")
_COURSE_CODE_RE = re.compile(
    r"\b(?!PAGE\s?\d{3}\b)[A-Z]{2,6}\s?\d{3}\b", re.IGNORECASE
)
_NON_ASSERTIVE_CONTEXT_RE = re.compile(
    r"\b(?:asked|question|whether|if|phrase|wording|quote|quoted|quotation)\b",
    re.IGNORECASE,
)
_QUESTION_START_RE = re.compile(
    r"^(?:is|are|was|were|does|do|can|could|may|might|would|will|should|"
    r"what|which|who|why|how|when|where|هل|ما|ماذا|كيف|لماذا|متى|أين|أي)\b",
    re.IGNORECASE,
)
_AUTHORITY_NEGATION_RE = re.compile(
    r"(?:\b(?:not|never|non|without|unapproved)\b)(?:[\s-]+[\w]+){0,4}[\s-]*$"
    r"|(?:\b(?:غير|ليس|ليست|لم|لا|بدون)\b)(?:\s+[\w]+){0,4}\s*$",
    re.IGNORECASE,
)
_NON_ASSERTIVE_TAIL_RE = re.compile(
    r"\b(?:not applicable|does not apply|doesn't apply|not supported|not the case)\b"
    r"|\b(?:غير منطبق|لا ينطبق|غير مدعوم)\b"
    r"|(?:=|:)\s*(?:false|no|غير)\b",
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
    "معتمدة نهائيا",
    "مؤكد رسميا",
    "مؤكدة رسميا",
    "الموافقة عليه رسميا",
    "الموافقة عليها رسميا",
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
    issues.extend(_fact_citation_issues(facts, text))
    issues = list(dict.fromkeys(issues))

    if not issues:
        return text, AdvisorGroundingAssessment(status="GROUNDED")
    return (
        _safe_facts_summary(facts, text),
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
    course_code = _course_code(fact.course)
    if fact.eligible is True and _has_asserted_claim(
        text,
        _NEGATIVE_ELIGIBILITY,
        course_code=course_code,
    ):
        return ["ELIGIBILITY_CONTRADICTION"]
    if fact.eligible is False and _has_asserted_claim(
        text,
        _POSITIVE_ELIGIBILITY,
        course_code=course_code,
    ):
        return ["ELIGIBILITY_CONTRADICTION"]
    if fact.eligible is None and _has_asserted_claim(
        text,
        (*_POSITIVE_ELIGIBILITY, *_NEGATIVE_ELIGIBILITY),
        course_code=course_code,
    ):
        return ["INDETERMINATE_ELIGIBILITY_PRESENTED_AS_DEFINITE"]
    return []


def _degree_audit_issues(
    fact: AdvisorDegreeAuditFacts,
    text: str,
) -> list[str]:
    issues: list[str] = []
    lowered = text.casefold()
    labels = {
        "completed": ("completed credits", "credits completed", "earned credits"),
        "required": ("required credits", "credits required"),
        "remaining": ("remaining credits", "credits remaining"),
    }
    for field_name, field_labels in labels.items():
        expected = fact.credits.get(field_name)
        if not isinstance(expected, (int, float)) or isinstance(expected, bool):
            continue
        for label in field_labels:
            match = re.search(
                rf"\b{re.escape(label)}\s*(?:are|is|:|=)?\s*(\d+(?:\.\d+)?)",
                text.casefold(),
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
        and any(
            claim in text.casefold()
            for claim in ("completed all requirements", "ready to graduate")
        )
    ):
        issues.append("DEGREE_AUDIT_STATUS_CONTRADICTION")
    return issues


def _course_coverage_issues(
    facts: AdvisorAcademicFacts,
    text: str,
) -> list[str]:
    issues: list[str] = []
    for fact in facts.course_information:
        prerequisite_status = fact.coverage.get("prerequisites")
        corequisite_status = fact.coverage.get("corequisites")
        prerequisite_payload = fact.prerequisites
        if (
            prerequisite_status == "COMPLETE"
            and (prerequisite_payload.get("rules") or prerequisite_payload.get("expression"))
            and _has_asserted_claim(
                text,
                _NO_PREREQUISITE_CLAIMS,
                course_code=_course_code(fact.course),
            )
        ):
            issues.append("PREREQUISITE_DEFINITION_CONTRADICTION")
        if prerequisite_status != "COMPLETE" and _has_asserted_claim(
            text,
            _NO_PREREQUISITE_CLAIMS,
            course_code=_course_code(fact.course),
        ):
            issues.append("UNAVAILABLE_PREREQUISITES_PRESENTED_AS_ABSENT")
        if corequisite_status != "AVAILABLE" and _has_asserted_claim(
            text,
            _NO_COREQUISITE_CLAIMS,
            course_code=_course_code(fact.course),
        ):
            issues.append("UNAVAILABLE_COREQUISITES_PRESENTED_AS_ABSENT")

    if not facts.course_information and any(
        document.coverage_status != "AVAILABLE"
        and _has_asserted_claim(text, _NO_PREREQUISITE_CLAIMS)
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
    for fact in facts.eligibility:
        if not fact.authoritative and _has_asserted_claim(
            text,
            _AUTHORITATIVE_CLAIMS,
            course_code=_course_code(fact.course),
        ):
            return ["NON_AUTHORITATIVE_ELIGIBILITY_PRESENTED_AS_APPROVED"]
    for fact in facts.course_information:
        if not fact.authoritative and _has_asserted_claim(
            text,
            _AUTHORITATIVE_CLAIMS,
            course_code=_course_code(fact.course),
        ):
            return ["NON_AUTHORITATIVE_COURSE_FACTS_PRESENTED_AS_APPROVED"]
    if any(
        not fact.authoritative
        and _has_asserted_claim(text, _AUTHORITATIVE_CLAIMS)
        for fact in facts.degree_audit
    ):
        return ["NON_AUTHORITATIVE_AUDIT_PRESENTED_AS_APPROVED"]
    return []


def _review_attribution_issues(
    facts: AdvisorAcademicFacts,
    text: str,
) -> list[str]:
    if not _has_asserted_eligibility_review_claim(text):
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


def _fact_citation_issues(facts: AdvisorAcademicFacts, text: str) -> list[str]:
    """Keep explicit Planning citations attached to their own fact channel."""

    issues: list[str] = []
    for fact in facts.eligibility:
        issues.extend(
            _course_fact_citation_issues(
                text,
                _course_code(fact.course),
                fact.citations,
            )
        )
    for fact in facts.course_information:
        citations = list(fact.course_provenance)
        citations.extend(_planning_citations(fact.prerequisites.get("provenance")))
        for rule in fact.prerequisites.get("rules", []):
            if isinstance(rule, dict):
                citations.extend(_planning_citations([rule.get("provenance")]))
        issues.extend(
            _course_fact_citation_issues(
                text,
                _course_code(fact.course),
                citations,
            )
        )
    return issues


def _course_fact_citation_issues(
    text: str,
    course_code: str | None,
    citations: list[AdvisorPlanningCitation],
) -> list[str]:
    if course_code is None:
        return []
    expected = {
        (citation.source_id.casefold(), citation.page)
        for citation in citations
        if citation.source_id is not None and isinstance(citation.page, int)
    }
    if not expected:
        return []
    expected_sources = {source for source, _ in expected}
    issues: list[str] = []
    for sentence in _sentence_chunks(text):
        if course_code.casefold().replace(" ", "") not in {
            match.group(0).casefold().replace(" ", "")
            for match in _COURSE_CODE_RE.finditer(sentence)
        }:
            continue
        source_mentions = {
            _normalize_source(match.group(0))
            for match in _SOURCE_RE.finditer(sentence)
        }
        source_mentions.update(
            source
            for source in expected_sources
            if re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(source)}(?![A-Za-z0-9_])",
                sentence,
                re.IGNORECASE,
            )
        )
        pages = {int(match.group(1)) for match in _PAGE_RE.finditer(sentence)}
        if source_mentions and pages and any(
            (source, page) not in expected
            for source in source_mentions
            for page in pages
        ):
            issues.append("CITATION_FACT_MAPPING")
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


def _safe_facts_summary(facts: AdvisorAcademicFacts, source_text: str) -> str:
    if _prefers_arabic(source_text):
        return _safe_facts_summary_arabic(facts)

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


def _safe_facts_summary_arabic(facts: AdvisorAcademicFacts) -> str:
    lines = [
        "تعذر عرض الشرح المولد بأمان لأنه تعارض مع حقائق أكاديمية موثوقة. "
        "تظهر النتائج الموثوقة فقط:",
    ]
    for fact in facts.eligibility:
        course_code = fact.course.get("code", "المقرر المطلوب")
        authority = "معتمدة نهائياً" if fact.authoritative else "غير معتمدة نهائياً"
        review = "نعم" if fact.requires_human_review else "لا"
        lines.append(
            f"أهلية تسجيل {course_code}: {fact.decision} "
            f"(حالة الاعتماد: {authority}، تتطلب مراجعة بشرية: {review})."
        )
    for fact in facts.course_information:
        course_code = fact.course.get("code", "المقرر المطلوب")
        lines.append(
            f"معلومات {course_code}: تغطية المتطلبات السابقة="
            f"{fact.coverage.get('prerequisites', 'UNKNOWN')}؛ وتغطية المتطلبات المتزامنة="
            f"{fact.coverage.get('corequisites', 'UNKNOWN')}."
        )
    for fact in facts.degree_audit:
        review = "نعم" if fact.requires_human_review else "لا"
        lines.append(
            f"حالة تدقيق الدرجة: {fact.status}؛ الساعات المكتملة="
            f"{fact.credits.get('completed')}؛ الساعات المتبقية="
            f"{fact.credits.get('remaining')}؛ تتطلب مراجعة بشرية: {review}."
        )
    for fact in facts.official_documents:
        lines.append(
            "أدلة الوثائق الرسمية "
            + ("متاحة في حقل الأدلة المنظم." if fact.evidence_available else "غير متاحة.")
        )
    return " ".join(lines)


def _prefers_arabic(text: str) -> bool:
    arabic_count = len(re.findall(r"[\u0600-\u06ff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    return arabic_count > 0 and arabic_count >= latin_count


def _course_code(course: dict[str, object]) -> str | None:
    value = course.get("code")
    return value if isinstance(value, str) and value.strip() else None


def _has_asserted_claim(
    text: str,
    phrases: Iterable[str],
    *,
    course_code: str | None = None,
) -> bool:
    """Find a short asserted claim while ignoring questions and negation.

    This deliberately remains a narrow surface matcher.  It is not intended
    to understand arbitrary prose; it only avoids treating a negated,
    quoted, or question-shaped mention as a positive deterministic claim.
    """

    phrase_values = tuple(phrases)
    normalized_phrases = tuple(_normalize_matching_text(phrase) for phrase in phrase_values)
    for sentence in _sentence_chunks(text):
        normalized_sentence = _normalize_matching_text(sentence)
        for phrase, normalized_phrase in zip(phrase_values, normalized_phrases):
            if normalized_phrase not in normalized_sentence:
                continue
            if _non_assertive_sentence(sentence) or _negates_claim(
                sentence,
                normalized_phrase,
            ):
                continue
            if course_code and not _claim_applies_to_course(
                sentence,
                phrase,
                course_code,
            ):
                continue
            return True
    return False


def _has_asserted_eligibility_review_claim(text: str) -> bool:
    for sentence in _sentence_chunks(text):
        normalized = _normalize_matching_text(sentence)
        english_claim = bool(_ELIGIBILITY_REVIEW_CLAIM_RE.search(sentence))
        arabic_claim = (
            ("اهليه" in normalized or "اهلية" in normalized)
            and "مراجعة بشرية" in normalized
            and bool(re.search(r"\b(?:تتطلب|تحتاج)\b", normalized))
        )
        if not (english_claim or arabic_claim):
            continue
        if _non_assertive_sentence(sentence):
            continue
        if re.search(
            r"\b(?:does not|doesn't|do not|don't|not)\s+(?:require|need)\b"
            r"|\b(?:requires?|needs?)\s+no\b",
            normalized,
        ) or re.search(r"\bلا\s+(?:تتطلب|تحتاج)\b", normalized):
            continue
        return True
    return False


def _normalize_matching_text(value: str) -> str:
    normalized = value.casefold().replace("ـ", "")
    normalized = _ARABIC_DIACRITICS_RE.sub("", normalized)
    return normalized.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي"}))


def _sentence_chunks(text: str) -> list[str]:
    return [chunk for chunk in re.split(r"[.!?؟;\n]+", text) if chunk.strip()]


def _non_assertive_sentence(sentence: str) -> bool:
    normalized = _normalize_matching_text(sentence)
    if "?" in sentence or "؟" in sentence:
        return True
    if _QUESTION_START_RE.search(normalized):
        return True
    return bool(_NON_ASSERTIVE_CONTEXT_RE.search(normalized))


def _negates_claim(sentence: str, normalized_phrase: str) -> bool:
    normalized = _normalize_matching_text(sentence)
    position = normalized.find(normalized_phrase)
    if position < 0:
        return False
    prefix = normalized[max(0, position - 90) : position]
    suffix = normalized[position + len(normalized_phrase) : position + len(normalized_phrase) + 70]
    if _AUTHORITY_NEGATION_RE.search(prefix):
        return True
    return bool(_NON_ASSERTIVE_TAIL_RE.search(suffix))


def _claim_applies_to_course(
    sentence: str,
    phrase: str,
    course_code: str,
) -> bool:
    normalized_code = _normalize_matching_text(course_code).replace(" ", "")
    normalized_sentence = _normalize_matching_text(sentence)
    course_matches = [
        match
        for match in _COURSE_CODE_RE.finditer(sentence)
        if _normalize_matching_text(match.group(0)).replace(" ", "")
        == normalized_code
    ]
    all_courses = list(_COURSE_CODE_RE.finditer(sentence))
    if not all_courses:
        return True
    if not course_matches:
        return False
    phrase_position = normalized_sentence.find(_normalize_matching_text(phrase))
    if len(all_courses) == 1 or phrase_position < 0:
        return True
    # A comma/conjunction normally separates claims about different courses.
    fragment_start = 0
    fragment_end = len(sentence)
    original_phrase_position = sentence.casefold().find(phrase.casefold())
    if original_phrase_position >= 0:
        separators = re.compile(r",|;|\b(?:while|whereas|but)\b", re.IGNORECASE)
        before = [match.end() for match in separators.finditer(sentence, 0, original_phrase_position)]
        after_match = separators.search(sentence, original_phrase_position + len(phrase))
        fragment_start = max(before, default=0)
        fragment_end = after_match.start() if after_match else len(sentence)
    return any(
        fragment_start <= match.start() < fragment_end for match in course_matches
    )


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
