"""Deterministic grading helpers for grounded advisor live evaluations."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from app.llm.contracts import ToolCall
from app.orchestration.contracts import AdvisorResponse, AdvisorToolExecution

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
_COURSE_CODE_RE = re.compile(
    r"\b(?!PAGE\s?\d{3}\b)[A-Z]{2,6}\s?\d{3}\b", re.IGNORECASE
)
_SOURCE_RE = re.compile(
    r"\b(?:SRC|REG|DOC|BYLAW|RULE)[_-][A-Za-z0-9_.:/-]+\b", re.IGNORECASE
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
_TECHNICAL_LATIN_TERMS = (
    "gpa",
    "credits",
    "credit hours",
    "prerequisite",
    "prerequisites",
    "corequisite",
    "corequisites",
    "human review",
    "indeterminate",
    "eligible",
    "not eligible",
    "regulation",
    "regulations",
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
        "requested_tools_by_round": [],
        "executed_tools": [],
        "rejected_tool_calls": [],
        "tool_arguments": [],
        "tool_selected": None,
        "tool_executed": False,
        "tool_execution_count": 0,
        "tool_round_count": 0,
        "tool_result_available": False,
        "trusted_tool_summary": None,
        "trusted_tool_summaries": [],
        "final_answer": None,
        "response_language": None,
        "decision_preserved": None,
        "human_review_preserved": None,
        "citations_supported": None,
        "invented_academic_information": [],
        "reasons": [reason],
    }


def _grade_turn(
    *,
    case: Mapping[str, Any],
    response: AdvisorResponse,
    initial_tool_calls: Sequence[ToolCall],
    tool_calls_by_round: Sequence[Sequence[ToolCall]] | None = None,
    known_course_codes: Sequence[str] = (),
) -> dict[str, Any]:
    """Grade one completed orchestrator turn using deterministic facts."""

    requested_rounds = _requested_rounds(initial_tool_calls, tool_calls_by_round)
    requested_calls = [call for round_calls in requested_rounds for call in round_calls]
    records = _execution_records(response, requested_calls)
    selected_tools = [call.name for call in requested_calls]
    raw_arguments = [call.arguments for call in requested_calls]
    executed_records = [
        record for record in records if record.status in {"executed", "failed"}
    ]
    available_records = [
        record
        for record in executed_records
        if _is_available_result(record.result)
    ]
    summaries = [
        _summarize_tool_result(record.result) for record in records if record.result is not None
    ]
    summaries = [summary for summary in summaries if summary is not None]
    result: dict[str, Any] = {
        "case_id": str(case["id"]),
        "status": "PASS",
        "selected_tools": selected_tools,
        "requested_tools_by_round": [
            _tool_call_payload(round_calls) for round_calls in requested_rounds
        ],
        "executed_tools": [
            _safe_execution_record(record) for record in executed_records
        ],
        "rejected_tool_calls": [
            _safe_execution_record(record)
            for record in records
            if record.status == "rejected"
        ],
        "tool_arguments": [
            _safe_arguments(tool_name, arguments)
            for tool_name, arguments in zip(selected_tools, raw_arguments)
        ],
        "tool_selected": selected_tools[0] if len(selected_tools) == 1 else None,
        "tool_executed": bool(executed_records),
        "tool_execution_count": len(executed_records),
        "tool_round_count": len(requested_rounds),
        "tool_result_available": bool(available_records),
        "trusted_tool_summary": summaries[0] if len(summaries) == 1 else None,
        "trusted_tool_summaries": summaries,
        "final_answer": response.text,
        "response_language": detect_language(response.text),
        "decision_preserved": None,
        "human_review_preserved": None,
        "human_review_required": False,
        "human_review_warning_present": _has_review_warning(response.text),
        "citations_supported": None,
        "invented_academic_information": [],
        "reasons": [],
    }

    required_tools = _required_tools(case)
    if not required_tools:
        if selected_tools:
            return _fail(result, "unexpected_tool")
        if case.get("kind") == "clarification" and not _looks_like_clarification(
            response.text
        ):
            return _fail(result, "clarification_not_requested")
        result["decision_preserved"] = True
        return result

    for call in requested_calls:
        forbidden_keys = _forbidden_argument_keys(call.name, call.arguments)
        if forbidden_keys:
            return _fail(
                result,
                "trusted_argument_override_attempted",
                extra={"rejected_argument_keys": sorted(forbidden_keys)},
            )

    expected_set = set(required_tools)
    allowed_extra = set(case.get("allowed_extra_tools", []))
    missing_tools = [tool for tool in required_tools if tool not in selected_tools]
    if missing_tools:
        return _fail(result, "required_tool_not_requested")
    extra_tools = [
        tool
        for tool in selected_tools
        if tool not in expected_set and tool not in allowed_extra
    ]
    if extra_tools:
        _manual(result, "unjustified_extra_tool_call")

    for record in records:
        if record.status != "rejected":
            continue
        error_code = _tool_error_code(record.result)
        if error_code in {
            "REPEATED_TOOL_CALL",
            "TOOL_ROUND_LIMIT_EXCEEDED",
            "TOOL_EXECUTION_LIMIT_EXCEEDED",
        }:
            return _fail(result, "tool_execution_bound_exceeded")

    required_records: list[AdvisorToolExecution] = []
    for tool_name in required_tools:
        matching = [record for record in records if record.tool_name == tool_name]
        if not matching:
            return _fail(result, "tool_result_missing")
        required_records.append(matching[0])

    available_results: list[tuple[str, Mapping[str, Any]]] = []
    for record in required_records:
        tool_result = record.result
        error_code = _tool_error_code(tool_result)
        if record.status == "rejected":
            if error_code == "INVALID_TOOL_ARGUMENTS":
                return _fail(result, "invalid_tool_arguments")
            if error_code in {"REPEATED_TOOL_CALL", "TOOL_ROUND_LIMIT_EXCEEDED", "TOOL_EXECUTION_LIMIT_EXCEEDED"}:
                return _fail(result, "tool_execution_bound_exceeded")
            return _fail(result, "tool_call_rejected")
        if not _is_available_result(tool_result):
            if error_code == "INVALID_TOOL_ARGUMENTS":
                return _fail(result, "invalid_tool_arguments")
            _manual(result, "tool_result_unavailable")
            continue
        shape_error = _tool_result_shape_error(record.tool_name, tool_result)
        if shape_error is not None:
            _manual(result, shape_error)
        available_results.append((record.tool_name, tool_result))

    formal_review = any(_requires_review(tool_result) for _, tool_result in available_results)
    result["human_review_required"] = formal_review
    result["human_review_preserved"] = (
        result["human_review_warning_present"] if formal_review else None
    )
    if formal_review and not result["human_review_warning_present"]:
        _fail(result, "human_review_warning_missing")
    if formal_review and not response.requires_human_review:
        _manual(result, "response_human_review_flag_lost")
    if not formal_review and response.requires_human_review:
        _manual(result, "unsubstantiated_human_review_flag")
    if formal_review:
        _manual(result, "formal_human_review_requires_manual_review")

    for _, tool_result in available_results:
        contradiction = _contradicts_tool_result(tool_result, response.text)
        if contradiction:
            result["decision_preserved"] = False
            return _fail(result, "final_answer_contradicts_tool_result")
    result["decision_preserved"] = bool(available_results)

    for _, tool_result in available_results:
        if _indeterminate_answer_requires_review(tool_result, response.text):
            _manual(result, "indeterminate_decision_requires_manual_review")
        if _claims_non_authoritative_data_is_authoritative(tool_result, response.text):
            _manual(result, "non_authoritative_result_requires_manual_review")

    search_results = [
        tool_result
        for tool_name, tool_result in available_results
        if tool_name == "search_official_documents"
    ]
    if search_results:
        combined_evidence = {
            "results": [
                item
                for tool_result in search_results
                for item in tool_result.get("results", [])
                if isinstance(item, Mapping)
            ]
        }
        if not combined_evidence["results"]:
            result["citations_supported"] = None
            _manual(result, "retrieval_no_evidence")
        else:
            citation_state, citation_reason = _grade_citations(
                combined_evidence,
                response.text,
            )
            result["citations_supported"] = citation_state
            if citation_reason == "unsupported_citation":
                return _fail(result, citation_reason)
            if citation_reason is not None:
                _manual(result, citation_reason)

    for tool_name, tool_result in available_results:
        if tool_name == "degree_audit":
            degree_reason = _grade_degree_audit_consistency(tool_result, response.text)
            if degree_reason == "degree_audit_deterministic_contradiction":
                return _fail(result, degree_reason)
            if degree_reason is not None:
                _manual(result, degree_reason)

    invented: list[str] = []
    for tool_name, tool_result in available_results:
        invented.extend(
            _detect_invented_information(
                case=case,
                answer=response.text,
                tool_result=tool_result,
                known_course_codes=known_course_codes,
            )
        )
    result["invented_academic_information"] = list(dict.fromkeys(invented))
    if invented:
        _manual(result, "heuristic_academic_claim_requires_review")

    if case.get("kind") in {
        "eligibility",
        "degree_audit",
        "official_documents",
        "trusted_override",
    }:
        _manual(result, "narrative_requires_manual_review")

    return result


def grade_turn(
    *,
    case: Mapping[str, Any],
    response: AdvisorResponse,
    initial_tool_calls: Sequence[ToolCall],
    tool_calls_by_round: Sequence[Sequence[ToolCall]] | None = None,
    known_course_codes: Sequence[str] = (),
) -> dict[str, Any]:
    """Grade one turn and always record the expected/observed language pair."""

    result = _grade_turn(
        case=case,
        response=response,
        initial_tool_calls=initial_tool_calls,
        tool_calls_by_round=tool_calls_by_round,
        known_course_codes=known_course_codes,
    )
    return _apply_language_grade(result, case)


def detect_language(text: str) -> str:
    """Classify the visible answer as English, Arabic, mixed, or unknown."""

    has_arabic = bool(_ARABIC_RE.search(text))
    latin_text = _remove_technical_latin(text)
    has_latin = bool(_LATIN_RE.search(latin_text))
    if has_arabic and has_latin:
        return "mixed"
    if has_arabic:
        return "ar"
    if has_latin:
        return "en"
    return "unknown"


def _remove_technical_latin(text: str) -> str:
    """Ignore course codes and short academic terms in Arabic prose."""

    scrubbed = _COURSE_CODE_RE.sub(" ", text)
    scrubbed = _SOURCE_RE.sub(" ", scrubbed)
    scrubbed = re.sub(r"\bpage\s?\d+\b", " ", scrubbed, flags=re.IGNORECASE)
    scrubbed = re.sub(r"\b\d+(?:\.\d+)?\b", " ", scrubbed)
    for term in _TECHNICAL_LATIN_TERMS:
        scrubbed = re.sub(re.escape(term), " ", scrubbed, flags=re.IGNORECASE)
    return scrubbed


def _apply_language_grade(
    result: dict[str, Any],
    case: Mapping[str, Any],
) -> dict[str, Any]:
    expected = case.get("language_expected")
    actual = result.get("response_language")
    result["language_expected"] = expected
    result["language_match"] = (
        None if expected is None else actual == expected
    )
    if expected is not None and actual != expected:
        if "response_language_mismatch" not in result["reasons"]:
            result["reasons"].append("response_language_mismatch")
        if result["status"] == "PASS":
            result["status"] = "NEEDS_MANUAL_REVIEW"
    return result


def _requested_rounds(
    initial_tool_calls: Sequence[ToolCall],
    tool_calls_by_round: Sequence[Sequence[ToolCall]] | None,
) -> list[list[ToolCall]]:
    if tool_calls_by_round is not None:
        return [list(round_calls) for round_calls in tool_calls_by_round]
    return [list(initial_tool_calls)] if initial_tool_calls else []


def _execution_records(
    response: AdvisorResponse,
    requested_calls: Sequence[ToolCall],
) -> list[AdvisorToolExecution]:
    if response.tool_executions:
        return list(response.tool_executions)
    if response.tool_name is None:
        return []

    result = response.tool_result
    error_code = _tool_error_code(result)
    if error_code in {
        "UNKNOWN_TOOL",
        "INVALID_TOOL_ARGUMENTS",
        "REPEATED_TOOL_CALL",
        "TOOL_ROUND_LIMIT_EXCEEDED",
        "TOOL_EXECUTION_LIMIT_EXCEEDED",
    }:
        status = "rejected"
    elif isinstance(result, Mapping) and "error" in result:
        status = "failed"
    else:
        status = "executed"
    arguments = next(
        (call.arguments for call in requested_calls if call.name == response.tool_name),
        {},
    )
    return [
        AdvisorToolExecution(
            call_id=(
                next(
                    (
                        call.call_id
                        for call in requested_calls
                        if call.name == response.tool_name and call.call_id
                    ),
                    None,
                )
                or "legacy-call-1"
            ),
            tool_name=response.tool_name,
            arguments=dict(arguments),
            status=status,
            round_index=1,
            result=result,
        )
    ]


def _required_tools(case: Mapping[str, Any]) -> list[str]:
    configured = case.get("required_tools")
    if isinstance(configured, Sequence) and not isinstance(configured, (str, bytes)):
        return [str(tool) for tool in configured]
    expected = case.get("expected_tool")
    if expected is None:
        return []
    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes)):
        return [str(tool) for tool in expected]
    return [str(expected)]


def _safe_execution_record(record: AdvisorToolExecution) -> dict[str, Any]:
    return {
        "tool_name": record.tool_name,
        "status": record.status,
        "round_index": record.round_index,
        "arguments": _safe_arguments(record.tool_name, record.arguments),
        "result": _summarize_tool_result(record.result),
    }


def _tool_call_payload(calls: Sequence[ToolCall]) -> list[dict[str, Any]]:
    return [
        {"name": call.name, "arguments": _safe_arguments(call.name, call.arguments)}
        for call in calls
    ]


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
    if re.search(
        r"\b(?:not|isn't|is not)\s+(?:fully\s+)?(?:officially\s+)?authoritative\b",
        lowered,
    ):
        return False
    return any(claim.casefold() in lowered for claim in positive_claims) and not any(
        claim.casefold() in lowered for claim in negative_claims
    )


def _grade_degree_audit_consistency(
    tool_result: Mapping[str, Any],
    answer: str,
) -> str | None:
    credits = tool_result.get("credits")
    if isinstance(credits, Mapping):
        for field_name, labels in {
            "completed": ("completed credits", "credits completed", "earned credits"),
            "required": ("required credits", "credits required"),
            "remaining": ("remaining credits", "credits remaining"),
        }.items():
            expected = credits.get(field_name)
            if not isinstance(expected, (int, float)):
                continue
            for label in labels:
                match = re.search(
                    rf"\b{re.escape(label)}\s*(?:are|is|:|=)?\s*(\d+(?:\.\d+)?)",
                    answer,
                    re.IGNORECASE,
                )
                if match and float(match.group(1)) != float(expected):
                    return "degree_audit_deterministic_contradiction"

    requirements = tool_result.get("requirements")
    if isinstance(requirements, Mapping):
        satisfied = requirements.get("satisfied_count")
        total = requirements.get("total_count")
        if isinstance(satisfied, int) and isinstance(total, int):
            summary_match = re.search(
                r"\b(\d+)\s+of\s+(\d+)\s+(?:known\s+)?requirements?\b",
                answer,
                re.IGNORECASE,
            )
            if summary_match and (
                int(summary_match.group(1)) != satisfied
                or int(summary_match.group(2)) != total
            ):
                return "degree_audit_deterministic_contradiction"

    citations = tool_result.get("citations")
    if not isinstance(citations, list):
        return None
    trusted_by_rule: dict[str, set[tuple[str | None, int | None]]] = {}
    trusted_sources: set[str] = set()
    for citation in citations:
        if not isinstance(citation, Mapping) or not citation.get("rule_id"):
            continue
        rule_id = str(citation["rule_id"]).casefold()
        source_id = citation.get("source_id")
        normalized_source = str(source_id).casefold() if source_id else None
        page = citation.get("page")
        normalized_page = page if isinstance(page, int) else None
        trusted_by_rule.setdefault(rule_id, set()).add(
            (normalized_source, normalized_page)
        )
        if normalized_source:
            trusted_sources.add(normalized_source)

    for rule_match in re.finditer(r"\bREQ[0-9]+[-_][0-9A-Z_-]+\b", answer, re.IGNORECASE):
        rule_id = rule_match.group(0).casefold()
        trusted = trusted_by_rule.get(rule_id)
        if not trusted:
            continue
        sentence_start = max(
            answer.rfind(".", 0, rule_match.start()),
            answer.rfind(";", 0, rule_match.start()),
            answer.rfind("\n", 0, rule_match.start()),
        )
        sentence_end_candidates = [
            position
            for separator in (".", ";", "\n")
            for position in [answer.find(separator, rule_match.end())]
            if position != -1
        ]
        sentence_end = min(sentence_end_candidates, default=len(answer))
        pages = [
            int(match.group(1))
            for match in _PAGE_RE.finditer(answer[sentence_start + 1 : sentence_end])
        ]
        source_mentions = {
            _normalize_source_token(match.group(0))
            for match in _SOURCE_RE.finditer(answer[sentence_start + 1 : sentence_end])
        }
        if len(pages) > 1 or len(source_mentions) > 1:
            return "degree_audit_citation_requires_manual_review"
        if pages:
            page = pages[0]
            if not any(expected_page == page for _, expected_page in trusted):
                return "degree_audit_deterministic_contradiction"
            if source_mentions and not any(
                source in trusted_sources and (source, page) in trusted
                for source in source_mentions
            ):
                return "degree_audit_deterministic_contradiction"
        else:
            return "degree_audit_citation_requires_manual_review"
    return None


def _grade_citations(
    tool_result: Mapping[str, Any],
    answer: str,
) -> tuple[bool | None, str | None]:
    evidence = tool_result.get("results")
    if not isinstance(evidence, list):
        return False, "citation_evidence_missing"

    source_ranges: dict[str, list[tuple[int, int]]] = {}
    for item in evidence:
        if not isinstance(item, Mapping) or not item.get("source_id"):
            continue
        source_id = str(item["source_id"])
        normalized_source = source_id.casefold()
        start = item.get("page_start")
        end = item.get("page_end")
        if isinstance(start, int) and isinstance(end, int):
            source_ranges.setdefault(normalized_source, []).append((start, end))
        elif isinstance(start, int):
            source_ranges.setdefault(normalized_source, []).append((start, start))
        elif isinstance(end, int):
            source_ranges.setdefault(normalized_source, []).append((end, end))
        else:
            source_ranges.setdefault(normalized_source, [])

    if not source_ranges:
        return False, "citation_evidence_missing"

    source_mentions = _source_mentions(answer, source_ranges)
    mentioned_pattern_sources = {
        _normalize_source_token(source)
        for source in _SOURCE_RE.findall(answer)
    }
    if mentioned_pattern_sources - set(source_ranges):
        return False, "unsupported_citation"

    page_mentions = list(_PAGE_RE.finditer(answer))
    if not source_mentions and not page_mentions:
        return False, "citation_not_present"

    if not page_mentions:
        return None, "ambiguous_citation"

    for page_match in page_mentions:
        page = int(page_match.group(1))
        candidate_sources = _candidate_sources_for_page(
            answer,
            page_match.start(),
            source_mentions,
        )
        if not candidate_sources:
            return None, "ambiguous_citation"
        if len(candidate_sources) > 1:
            return None, "ambiguous_citation"

        source_id = next(iter(candidate_sources))
        ranges = source_ranges[source_id]
        if not ranges or not any(start <= page <= end for start, end in ranges):
            return False, "unsupported_citation"

    return True, None


def _source_mentions(
    answer: str,
    source_ranges: Mapping[str, Sequence[tuple[int, int]]],
) -> list[tuple[str, int, int]]:
    mentions: list[tuple[str, int, int]] = []
    for source_id in source_ranges:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(source_id)}(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )
        mentions.extend(
            (source_id, match.start(), match.end())
            for match in pattern.finditer(answer)
        )

    for token_match in _SOURCE_RE.finditer(answer):
        normalized = _normalize_source_token(token_match.group(0))
        if normalized in source_ranges and not any(
            start == token_match.start() and end == token_match.end()
            for _, start, end in mentions
        ):
            mentions.append((normalized, token_match.start(), token_match.end()))
    return sorted(mentions, key=lambda mention: mention[1])


def _normalize_source_token(token: str) -> str:
    return token.rstrip(".,;:)]}").casefold()


def _candidate_sources_for_page(
    answer: str,
    page_position: int,
    source_mentions: Sequence[tuple[str, int, int]],
) -> set[str]:
    start = max(
        answer.rfind(".", 0, page_position),
        answer.rfind("!", 0, page_position),
        answer.rfind("?", 0, page_position),
        answer.rfind(";", 0, page_position),
        answer.rfind("\n", 0, page_position),
    )
    end_candidates = [
        position
        for separator in (".", "!", "?", ";", "\n")
        for position in [answer.find(separator, page_position)]
        if position != -1
    ]
    end = min(end_candidates, default=len(answer))
    page_positions = [
        match.start()
        for match in _PAGE_RE.finditer(answer)
        if start < match.start() < end
    ]
    direct_sources = []
    for source_id, source_start, source_end in source_mentions:
        if not (start < source_start < source_end < page_position < end):
            continue
        if any(source_end < other_page < page_position for other_page in page_positions):
            continue
        direct_sources.append(source_id)
    return set(direct_sources)


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
