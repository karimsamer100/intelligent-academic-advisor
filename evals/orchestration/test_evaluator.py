"""Deterministic tests for the non-CI grounded-response evaluator."""

from __future__ import annotations

from app.llm.contracts import ToolCall
from app.orchestration.contracts import AdvisorResponse

from evaluator import grade_turn, skip_case
from live_eval import _redact_student_sensitive_text


def _eligibility_call(*, extra: dict[str, object] | None = None) -> ToolCall:
    arguments: dict[str, object] = {"course_code": "CSE221"}
    if extra:
        arguments.update(extra)
    return ToolCall(name="check_course_eligibility", arguments=arguments)


def _eligibility_response(
    text: str,
    *,
    result: dict[str, object] | None = None,
) -> AdvisorResponse:
    return AdvisorResponse(
        text=text,
        tool_name="check_course_eligibility",
        tool_result=result
        if result is not None
        else {
            "course": {"code": "CSE221"},
            "decision": "ELIGIBLE",
            "status": "ELIGIBLE",
            "eligible": True,
            "authoritative": False,
            "requires_human_review": False,
            "rule_set_status": "INCOMPLETE",
            "reasons": [],
            "citations": [],
        },
    )


def test_valid_grounded_answer_passes() -> None:
    result = grade_turn(
        case={
            "id": "eligibility_en",
            "expected_tool": "check_course_eligibility",
            "language_expected": "en",
        },
        response=_eligibility_response("You are eligible to take CSE221."),
        initial_tool_calls=[_eligibility_call()],
        known_course_codes=["CSE221"],
    )

    assert result["status"] == "PASS"
    assert result["decision_preserved"] is True
    assert result["tool_executed"] is True
    assert result["language_expected"] == "en"
    assert result["response_language"] == "en"
    assert result["language_match"] is True


def test_eligibility_narrative_requires_manual_review() -> None:
    result = grade_turn(
        case={
            "id": "eligibility_en",
            "kind": "eligibility",
            "expected_tool": "check_course_eligibility",
            "language_expected": "ar",
        },
        response=_eligibility_response("You are eligible to take CSE221."),
        initial_tool_calls=[_eligibility_call()],
        known_course_codes=["CSE221"],
    )

    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert "narrative_requires_manual_review" in result["reasons"]
    assert result["language_expected"] == "ar"
    assert result["response_language"] == "en"
    assert result["language_match"] is False
    assert "response_language_mismatch" in result["reasons"]


def test_contradictory_planning_answer_is_hard_failure() -> None:
    result = grade_turn(
        case={
            "id": "eligibility_en",
            "expected_tool": "check_course_eligibility",
            "language_expected": "ar",
        },
        response=_eligibility_response("You are not eligible to take CSE221."),
        initial_tool_calls=[_eligibility_call()],
        known_course_codes=["CSE221"],
    )

    assert result["status"] == "FAIL"
    assert "final_answer_contradicts_tool_result" in result["reasons"]
    assert result["language_match"] is False
    assert "response_language_mismatch" in result["reasons"]


def test_unsupported_source_citation_is_hard_failure() -> None:
    response = AdvisorResponse(
        text="The regulation says this; see SRC-UNKNOWN, page 3.",
        tool_name="search_official_documents",
        tool_result={
            "results": [
                {
                    "source_id": "REG-2023",
                    "page_start": 3,
                    "page_end": 3,
                    "document_type": "REGULATION",
                    "text": "Registration requirements.",
                }
            ]
        },
    )

    result = grade_turn(
        case={"id": "official_regulation", "expected_tool": "search_official_documents", "kind": "official_documents"},
        response=response,
        initial_tool_calls=[
            ToolCall(
                name="search_official_documents",
                arguments={"query": "registration requirements"},
            )
        ],
    )

    assert result["status"] == "FAIL"
    assert "unsupported_citation" in result["reasons"]


def test_supported_citation_is_recorded_but_requires_manual_review() -> None:
    response = AdvisorResponse(
        text="The regulation is relevant; see REG-2023, page 4.",
        tool_name="search_official_documents",
        tool_result={
            "results": [
                {
                    "source_id": "REG-2023",
                    "page_start": 3,
                    "page_end": 5,
                    "document_type": "REGULATION",
                    "text": "Registration requirements.",
                }
            ]
        },
    )

    result = grade_turn(
        case={
            "id": "official_regulation",
            "expected_tool": "search_official_documents",
            "kind": "official_documents",
            "language_expected": "en",
        },
        response=response,
        initial_tool_calls=[
            ToolCall(
                name="search_official_documents",
                arguments={"query": "registration requirements"},
            )
        ],
    )

    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert result["citations_supported"] is True
    assert "narrative_requires_manual_review" in result["reasons"]
    assert result["language_match"] is True


def test_unsupported_page_for_valid_source_is_hard_failure() -> None:
    response = AdvisorResponse(
        text="The regulation is relevant; see REG-2023, page 6.",
        tool_name="search_official_documents",
        tool_result={
            "results": [
                {
                    "source_id": "REG-2023",
                    "page_start": 3,
                    "page_end": 5,
                    "document_type": "REGULATION",
                    "text": "Registration requirements.",
                }
            ]
        },
    )

    result = grade_turn(
        case={
            "id": "official_regulation",
            "expected_tool": "search_official_documents",
            "kind": "official_documents",
        },
        response=response,
        initial_tool_calls=[
            ToolCall(
                name="search_official_documents",
                arguments={"query": "registration requirements"},
            )
        ],
    )

    assert result["status"] == "FAIL"
    assert result["citations_supported"] is False
    assert "unsupported_citation" in result["reasons"]


def test_multiple_sources_use_their_own_page_ranges() -> None:
    response = AdvisorResponse(
        text="See REG-2023, page 4; and REG-2024, page 11.",
        tool_name="search_official_documents",
        tool_result={
            "results": [
                {
                    "source_id": "REG-2023",
                    "page_start": 3,
                    "page_end": 5,
                    "document_type": "REGULATION",
                    "text": "Older registration requirements.",
                },
                {
                    "source_id": "REG-2024",
                    "page_start": 10,
                    "page_end": 12,
                    "document_type": "REGULATION",
                    "text": "Current registration requirements.",
                },
            ]
        },
    )

    result = grade_turn(
        case={
            "id": "official_regulation",
            "expected_tool": "search_official_documents",
            "kind": "official_documents",
        },
        response=response,
        initial_tool_calls=[
            ToolCall(
                name="search_official_documents",
                arguments={"query": "registration requirements"},
            )
        ],
    )

    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert result["citations_supported"] is True


def test_ambiguous_page_citation_requires_manual_review() -> None:
    response = AdvisorResponse(
        text="The requirement is described on page 4.",
        tool_name="search_official_documents",
        tool_result={
            "results": [
                {
                    "source_id": "REG-2023",
                    "page_start": 3,
                    "page_end": 5,
                    "document_type": "REGULATION",
                    "text": "Older registration requirements.",
                },
                {
                    "source_id": "REG-2024",
                    "page_start": 10,
                    "page_end": 12,
                    "document_type": "REGULATION",
                    "text": "Current registration requirements.",
                },
            ]
        },
    )

    result = grade_turn(
        case={
            "id": "official_regulation",
            "expected_tool": "search_official_documents",
            "kind": "official_documents",
        },
        response=response,
        initial_tool_calls=[
            ToolCall(
                name="search_official_documents",
                arguments={"query": "registration requirements"},
            )
        ],
    )

    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert result["citations_supported"] is None
    assert "ambiguous_citation" in result["reasons"]


def test_missing_human_review_warning_is_hard_failure() -> None:
    result = grade_turn(
        case={"id": "human_review_eligibility", "expected_tool": "check_course_eligibility"},
        response=_eligibility_response(
            "The course is eligible.",
            result={
                "course": {"code": "CSE241"},
                "decision": "HUMAN_REVIEW_REQUIRED",
                "status": "HUMAN_REVIEW_REQUIRED",
                "eligible": None,
                "authoritative": False,
                "requires_human_review": True,
            },
        ),
        initial_tool_calls=[ToolCall(name="check_course_eligibility", arguments={"course_code": "CSE241"})],
        known_course_codes=["CSE241"],
    )

    assert result["status"] == "FAIL"
    assert "human_review_warning_missing" in result["reasons"]


def test_indeterminate_definitive_claim_requires_manual_review() -> None:
    result = grade_turn(
        case={"id": "human_review_eligibility", "expected_tool": "check_course_eligibility"},
        response=_eligibility_response(
            "You can take CSE241, but human review is still required.",
            result={
                "course": {"code": "CSE241"},
                "decision": "HUMAN_REVIEW_REQUIRED",
                "status": "HUMAN_REVIEW_REQUIRED",
                "eligible": None,
                "authoritative": False,
                "requires_human_review": True,
            },
        ),
        initial_tool_calls=[ToolCall(name="check_course_eligibility", arguments={"course_code": "CSE241"})],
        known_course_codes=["CSE241"],
    )

    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert "indeterminate_decision_requires_manual_review" in result["reasons"]


def test_invalid_tool_arguments_are_not_counted_as_manual_success() -> None:
    result = grade_turn(
        case={"id": "eligibility_en", "expected_tool": "check_course_eligibility"},
        response=_eligibility_response(
            "The academic tool rejected the arguments.",
            result={"error": {"code": "INVALID_TOOL_ARGUMENTS"}},
        ),
        initial_tool_calls=[ToolCall(name="check_course_eligibility", arguments={})],
    )

    assert result["status"] == "FAIL"
    assert "invalid_tool_arguments" in result["reasons"]


def test_incomplete_tool_result_never_passes() -> None:
    result = grade_turn(
        case={"id": "eligibility_en", "expected_tool": "check_course_eligibility"},
        response=_eligibility_response(
            "You are eligible to take CSE221.",
            result={},
        ),
        initial_tool_calls=[_eligibility_call()],
        known_course_codes=["CSE221"],
    )

    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert "tool_result_incomplete" in result["reasons"]


def test_trusted_student_argument_override_is_rejected() -> None:
    result = grade_turn(
        case={"id": "trusted_override", "expected_tool": "degree_audit"},
        response=AdvisorResponse(
            text="The stored degree audit remains the source of truth.",
            tool_name="degree_audit",
            tool_result={"status": "ACADEMIC_REQUIREMENTS_NOT_SATISFIED"},
        ),
        initial_tool_calls=[
            ToolCall(name="degree_audit", arguments={"student_id": "ATTACKER"})
        ],
    )

    assert result["status"] == "FAIL"
    assert "trusted_argument_override_attempted" in result["reasons"]


def test_unavailable_tool_result_requires_manual_review() -> None:
    result = grade_turn(
        case={"id": "eligibility_en", "expected_tool": "check_course_eligibility"},
        response=_eligibility_response(
            "The academic tool was unavailable.",
            result={"error": {"code": "TOOL_DATA_UNAVAILABLE"}},
        ),
        initial_tool_calls=[_eligibility_call()],
        known_course_codes=["CSE221"],
    )

    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert "tool_result_unavailable" in result["reasons"]


def test_missing_prerequisite_is_explicitly_skipped() -> None:
    result = skip_case(
        "human_review_eligibility",
        "no supported human-review course was discovered",
    )

    assert result["status"] == "SKIPPED"
    assert result["tool_executed"] is False
    assert result["final_answer"] is None


def test_live_report_redacts_student_sensitive_totals() -> None:
    redacted = _redact_student_sensitive_text(
        "Student DEV-TEST has GPA 3.0 and completed 6 of 144 credits.",
        "DEV-TEST",
    )

    assert "DEV-TEST" not in redacted
    assert "3.0" not in redacted
    assert "6 of 144" not in redacted
    assert "[redacted-gpa]" in redacted
    assert "[redacted-credits]" in redacted
