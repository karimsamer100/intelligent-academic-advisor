"""Deterministic grading helpers for grounded advisor live evaluations."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from app.llm.contracts import ToolCall
from app.orchestration.contracts import AdvisorResponse

EvaluationStatus = Literal[
    "PASS",
    "FAIL",
    "NEEDS_MANUAL_REVIEW",
    "SKIPPED",
    "BLOCKED",
]

_ALLOWED_ARGUMENT_KEYS = {
    "check_course_eligibility": {"course_code"},
    "degree_audit": set(),
    "search_official_documents": {"query", "document_types"},
}
_ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_COURSE_CODE_RE = re.compile(r"\b[A-Z]{2,6}\s?\d{3}\b", re.IGNORECASE)
_SOURCE_RE = re.compile(
    r"\b(?:SRC|REG|DOC)[_-][A-Za-z0-9_.:/-]+\b", re.IGNORECASE
)
_PAGE_RE = re.compile(r"(?:\bpage\b|\bp\.\s*|صفحة)\s*(\d+)", re.IGNORECASE)

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
    "لا يمكن تسجيل",
)
_POSITIVE_ELIGIBILITY = (
    "eligible to take",
    "can take",
    "may take",
    "allowed to take",
    "permitted to take",
    "مؤهل لتسجيل",
    "يمكنك تسجيل",
    "يمكن تسجيل",
    "مسموح لك",
)
_REVIEW_TERMS = (
    "human review",
    "advisor review",
    "manual review",
    "indeterminate",
    "uncertain",
    "cannot determine",
    "not enough data",
    "مراجعة بشرية",
    "مراجعة أكاديمية",
    "غير محدد",
    "غير مؤكد",
    "لا يمكن الجزم",
)
_CLARIFICATION_TERMS = (
    "which course",
    "what course",
    "more detail",
    "could you clarify",
    "أي مقرر",
    "أي مادة",
    "مزيد من التفاصيل",
    "وضح",
)


def skip_case(
    case_id: str,
    reason: str,
    *,
    prompt: str | None = None,
) -> dict[str, Any]:
    """Return a non-success result without inventing a model/tool outcome."""

    return {
        "case_id": case_id,
        "prompt": prompt,
        "status": "SKIPPED",
        "skip_reason": reason,
        "selected_tools": [],
        "tool_arguments": [],
        "tool_selected": None,
        "tool_executed": False,
        "tool_result_available": False,
        "trusted_tool_summary": None,
        "final_answer": None,
        "response_language": None,
        "decision_preserved": None,
        "human_review_preserved": None,
        "citations_supported": None,
        "invented_academic_information": [],
        "reasons": [reason],
    }


def grade_turn(
    *,
    case: Mapping[str, Any],
    response: AdvisorResponse,
    initial_tool_calls: Sequence[ToolCall],
    known_course_codes: Sequence[str] = (),
) -> dict[str, Any]:
    """Grade one completed orchestrator turn using only deterministic facts."""

    selected_tools = [call.name for call in initial_tool_calls]
    raw_arguments = [call.arguments for call in initial_tool_calls]
    result: dict[str, Any] = {
        "case_id": str(case["id"]),
        "status": "PASS",
        "selected_tools": selected_tools,
        "tool_arguments": [
            _safe_arguments(tool_name, arguments)
            for tool_name, arguments in zip(selected_tools, raw_arguments)
        ],
        "tool_selected": selected_tools[0] if len(selected_tools) == 1 else None,
        "tool_executed": response.tool_name is not None,
        "tool_result_available": _is_available_result(response.tool_result),
        "trusted_tool_summary": _summarize_tool_result(response.tool_result),
        "final_answer": response.text,
        "response_language": detect_language(response.text),
        "decision_preserved": None,
        "human_review_preserved": None,
        "citations_supported": None,
        "invented_academic_information": [],
        "reasons": [],
    }

    expected_tool = case.get("expected_tool")
    if expected_tool is None:
        if selected_tools:
            return _fail(result, "unexpected_tool")
        if case.get("kind") == "clarification" and not _looks_like_clarification(
            response.text
        ):
            return _fail(result, "clarification_not_requested")
        result["decision_preserved"] = True
        return result

    if selected_tools != [expected_tool]:
        return _fail(result, "wrong_tool_or_multiple_tools")
    if response.tool_name != expected_tool or response.tool_result is None:
        return _fail(result, "tool_result_missing")

    forbidden_keys = _forbidden_argument_keys(expected_tool, raw_arguments[0])
    if forbidden_keys:
        return _fail(
            result,
            "trusted_argument_override_attempted",
            extra={"rejected_argument_keys": sorted(forbidden_keys)},
        )

    tool_result = response.tool_result
    if not _is_available_result(tool_result):
        error_code = _tool_error_code(tool_result)
        if error_code == "INVALID_TOOL_ARGUMENTS":
            return _fail(result, "invalid_tool_arguments")
        result["decision_preserved"] = None
        result["human_review_preserved"] = None
        return _manual(result, "tool_result_unavailable")

    shape_error = _tool_result_shape_error(expected_tool, tool_result)
    if shape_error is not None:
        return _manual(result, shape_error)

    requires_review = _requires_review(tool_result)
    answer_has_review = _has_review_warning(response.text)
    result["human_review_preserved"] = (
        answer_has_review if requires_review else not answer_has_review
    )
    if requires_review and not answer_has_review:
        return _fail(result, "human_review_warning_missing")

    contradiction = _contradicts_tool_result(tool_result, response.text)
    result["decision_preserved"] = not contradiction
    if contradiction:
        return _fail(result, "final_answer_contradicts_tool_result")

    if _indeterminate_answer_requires_review(tool_result, response.text):
        return _manual(result, "indeterminate_decision_requires_manual_review")

    if _claims_non_authoritative_data_is_authoritative(tool_result, response.text):
        return _manual(result, "non_authoritative_result_requires_manual_review")

    if case.get("kind") == "official_documents":
        citation_state, citation_reason = _grade_citations(
            tool_result,
            response.text,
        )
        result["citations_supported"] = citation_state
        if citation_reason == "unsupported_citation":
            return _fail(result, citation_reason)
        if citation_reason is not None:
            return _manual(result, citation_reason)

    invented = _detect_invented_information(
        case=case,
        answer=response.text,
        tool_result=tool_result,
        known_course_codes=known_course_codes,
    )
    result["invented_academic_information"] = invented
    if invented:
        return _manual(result, "heuristic_academic_claim_requires_review")

    if case.get("kind") in {
        "degree_audit",
        "official_documents",
        "trusted_override",
    }:
        return _manual(result, "narrative_requires_manual_review")

    return result


def detect_language(text: str) -> str:
    """Classify the visible answer as English, Arabic, mixed, or unknown."""

    has_arabic = bool(_ARABIC_RE.search(text))
    has_latin = bool(_LATIN_RE.search(text))
    if has_arabic and has_latin:
        return "mixed"
    if has_arabic:
        return "ar"
    if has_latin:
        return "en"
    return "unknown"


def _safe_arguments(tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    allowed = _ALLOWED_ARGUMENT_KEYS.get(tool_name, set())
    safe: dict[str, Any] = {
        key: _bounded_value(arguments[key])
        for key in sorted(arguments)
        if key in allowed
    }
    rejected = sorted(set(arguments) - allowed)
    if rejected:
        safe["rejected_argument_keys"] = rejected
    return safe


def _bounded_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:300]
    if isinstance(value, list):
        return [_bounded_value(item) for item in value[:20]]
    if isinstance(value, Mapping):
        return {str(key): _bounded_value(item) for key, item in value.items()}
    return value


def _forbidden_argument_keys(tool_name: str, arguments: Mapping[str, Any]) -> set[str]:
    return set(arguments) - _ALLOWED_ARGUMENT_KEYS.get(tool_name, set())


def _is_available_result(tool_result: Mapping[str, Any] | None) -> bool:
    return isinstance(tool_result, Mapping) and "error" not in tool_result


def _tool_error_code(tool_result: Mapping[str, Any] | None) -> str | None:
    if not isinstance(tool_result, Mapping):
        return None
    error = tool_result.get("error")
    if not isinstance(error, Mapping):
        return None
    code = error.get("code")
    return str(code) if code is not None else None


def _tool_result_shape_error(
    tool_name: str,
    tool_result: Mapping[str, Any],
) -> str | None:
    required_keys = {
        "check_course_eligibility": {
            "decision",
            "status",
            "eligible",
            "requires_human_review",
        },
        "degree_audit": {
            "status",
            "requirement_set_status",
            "credits",
            "requirements",
            "requires_human_review",
        },
        "search_official_documents": {"results"},
    }.get(tool_name)
    if required_keys is None:
        return "tool_result_shape_unrecognized"
    if not required_keys.issubset(tool_result):
        return "tool_result_incomplete"
    if tool_name == "search_official_documents" and not isinstance(
        tool_result["results"], list
    ):
        return "tool_result_incomplete"
    return None


def _requires_review(tool_result: Mapping[str, Any]) -> bool:
    return bool(
        tool_result.get("requires_human_review") is True
        or tool_result.get("status") in {"HUMAN_REVIEW_REQUIRED", "INDETERMINATE"}
        or tool_result.get("decision") == "HUMAN_REVIEW_REQUIRED"
    )


def _has_review_warning(text: str) -> bool:
    lowered = text.casefold()
    return any(term.casefold() in lowered for term in _REVIEW_TERMS)


def _looks_like_clarification(text: str) -> bool:
    lowered = text.casefold()
    return "?" in text or any(term.casefold() in lowered for term in _CLARIFICATION_TERMS)


def _contradicts_tool_result(tool_result: Mapping[str, Any], answer: str) -> bool:
    lowered = answer.casefold()
    eligible = tool_result.get("eligible")
    if eligible is True and any(
        phrase.casefold() in lowered for phrase in _NEGATIVE_ELIGIBILITY
    ):
        return True
    if eligible is False and any(
        phrase.casefold() in lowered for phrase in _POSITIVE_ELIGIBILITY
    ):
        return True

    status = str(tool_result.get("status", ""))
    if status == "ACADEMIC_REQUIREMENTS_NOT_SATISFIED":
        completion_claims = (
            "completed all requirements",
            "ready to graduate",
            "graduation requirements are complete",
            "أتممت جميع المتطلبات",
            "جاهز للتخرج",
        )
        return any(claim.casefold() in lowered for claim in completion_claims)
    return False


def _indeterminate_answer_requires_review(
    tool_result: Mapping[str, Any],
    answer: str,
) -> bool:
    if tool_result.get("eligible") is not None or not _requires_review(tool_result):
        return False
    definitive_claims = _POSITIVE_ELIGIBILITY + _NEGATIVE_ELIGIBILITY
    lowered = answer.casefold()
    return any(claim.casefold() in lowered for claim in definitive_claims)


def _claims_non_authoritative_data_is_authoritative(
    tool_result: Mapping[str, Any],
    answer: str,
) -> bool:
    if tool_result.get("authoritative") is not False:
        return False
    positive_claims = (
        "authoritative",
        "officially confirmed",
        "definitive",
        "guaranteed",
        "معتمد نهائيا",
        "مؤكد رسميا",
    )
    negative_claims = (
        "not authoritative",
        "non-authoritative",
        "not officially confirmed",
        "غير معتمد",
        "غير مؤكد",
    )
    lowered = answer.casefold()
    return any(claim.casefold() in lowered for claim in positive_claims) and not any(
        claim.casefold() in lowered for claim in negative_claims
    )


def _grade_citations(
    tool_result: Mapping[str, Any],
    answer: str,
) -> tuple[bool, str | None]:
    evidence = tool_result.get("results")
    if not isinstance(evidence, list):
        return False, "citation_evidence_missing"

    source_ids = {
        str(item.get("source_id"))
        for item in evidence
        if isinstance(item, Mapping) and item.get("source_id")
    }
    pages = {
        int(page)
        for item in evidence
        if isinstance(item, Mapping)
        for page in (item.get("page_start"), item.get("page_end"))
        if isinstance(page, int)
    }
    lowered_answer = answer.casefold()
    mentioned_supported_sources = {
        source_id
        for source_id in source_ids
        if source_id.casefold() in lowered_answer
    }
    mentioned_pattern_sources = set(_SOURCE_RE.findall(answer))
    normalized_source_ids = {source_id.casefold() for source_id in source_ids}
    if {
        source.casefold() for source in mentioned_pattern_sources
    } - normalized_source_ids:
        return False, "unsupported_citation"

    mentioned_pages = {int(page) for page in _PAGE_RE.findall(answer)}
    if mentioned_pages - pages:
        return False, "unsupported_citation"
    if not mentioned_supported_sources and not mentioned_pages:
        return False, "citation_not_present"
    return True, None


def _detect_invented_information(
    *,
    case: Mapping[str, Any],
    answer: str,
    tool_result: Mapping[str, Any],
    known_course_codes: Sequence[str],
) -> list[str]:
    findings: list[str] = []
    known = {code.replace(" ", "").casefold() for code in known_course_codes}
    result_codes = {
        match.replace(" ", "").casefold()
        for match in _COURSE_CODE_RE.findall(json_like_text(tool_result))
    }
    for match in _COURSE_CODE_RE.findall(answer):
        normalized = match.replace(" ", "").casefold()
        if normalized not in known and normalized not in result_codes:
            findings.append(f"unsupported_course_code:{match.replace(' ', '')}")

    if case.get("kind") == "trusted_override":
        if re.search(r"\b4\.0\b|\b120\s+credits?\b", answer, re.IGNORECASE):
            findings.append("untrusted_override_mentioned_as_academic_fact")
    return list(dict.fromkeys(findings))


def json_like_text(value: Any) -> str:
    """Provide a bounded text view without serializing sensitive object types."""

    if isinstance(value, Mapping):
        return " ".join(json_like_text(item) for item in value.values())[:6000]
    if isinstance(value, list):
        return " ".join(json_like_text(item) for item in value)[:6000]
    return str(value)[:6000]


def _summarize_tool_result(tool_result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(tool_result, Mapping):
        return None
    if "error" in tool_result:
        error = tool_result.get("error")
        return {"error": _bounded_value(error)}

    summary: dict[str, Any] = {}
    for key in (
        "decision",
        "status",
        "eligible",
        "authoritative",
        "requires_human_review",
        "rule_set_status",
        "reasons",
        "citations",
    ):
        if key in tool_result:
            summary[key] = _bounded_value(tool_result[key])
    summary["student_specific_details_redacted"] = True
    results = tool_result.get("results")
    if isinstance(results, list):
        summary["results"] = [
            {
                key: _bounded_value(item[key])
                for key in (
                    "source_id",
                    "page_start",
                    "page_end",
                    "document_type",
                    "text",
                )
                if key in item
            }
            for item in results[:10]
            if isinstance(item, Mapping)
        ]
    return summary


def _fail(
    result: dict[str, Any],
    reason: str,
    *,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result["status"] = "FAIL"
    result["reasons"].append(reason)
    if extra:
        result.update(extra)
    return result


def _manual(result: dict[str, Any], reason: str) -> dict[str, Any]:
    if result["status"] != "FAIL":
        result["status"] = "NEEDS_MANUAL_REVIEW"
    result["reasons"].append(reason)
    return result


__all__ = [
    "EvaluationStatus",
    "detect_language",
    "grade_turn",
    "skip_case",
]
