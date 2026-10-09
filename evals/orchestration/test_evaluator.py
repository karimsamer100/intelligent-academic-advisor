"""Deterministic tests for the non-CI grounded-response evaluator."""

from __future__ import annotations

from app.llm.contracts import ToolCall
from app.orchestration.contracts import AdvisorResponse, AdvisorToolExecution

from evaluator import detect_language, grade_turn, skip_case
from live_eval import (
    Discovery,
    _blocked_case_result,
    _blocked_payload,
    _case_report_prompt,
    _redact_student_sensitive_text,
    _safe_report_prompt,
    _select_cases,
)


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


def test_case_id_selection_is_explicit_and_deterministic() -> None:
    selected = _select_cases(
        [{"id": "first", "prompt": "one"}, {"id": "second", "prompt": "two"}],
        ["second"],
    )

    assert selected == [{"id": "second", "prompt": "two"}]


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


def test_persisted_prompts_are_redacted_on_normal_blocked_and_skipped_paths() -> None:
    raw_prompt = "Student DEV-TEST has GPA 4.0 and 120 credits."
    expected = "Student [redacted-student] has [redacted-gpa] and [redacted-credits]."
    discovery = Discovery(
        student_id="DEV-TEST",
        regulation=2018,
        program="CS",
        course_codes=(),
        eligibility_course=None,
        review_course=None,
        student_count=1,
        valid_student_count=1,
        rag_available=False,
        rag_reason="test",
    )

    assert _safe_report_prompt(raw_prompt, "DEV-TEST") == expected

    blocked = _blocked_case_result(
        case={"id": "blocked"},
        prompt=raw_prompt,
        student_id="DEV-TEST",
        provider=None,
        response=None,
        error=RuntimeError("provider unavailable"),
    )
    assert blocked["prompt"] == expected

    skipped_prompt = _case_report_prompt({"prompt": raw_prompt}, discovery)
    assert skipped_prompt == expected

    blocked_payload = _blocked_payload(
        [{"id": "blocked-before-discovery", "prompt": raw_prompt}],
        "application dependency unavailable",
    )
    assert blocked_payload["cases"][0]["prompt"] is None


def test_page_token_is_not_classified_as_an_unsupported_course_code() -> None:
    result = grade_turn(
        case={"id": "eligibility_en", "expected_tool": "check_course_eligibility"},
        response=_eligibility_response(
            "You are eligible to take CSE221; see page161 in the returned record."
        ),
        initial_tool_calls=[_eligibility_call()],
        known_course_codes=["CSE221"],
    )

    assert "unsupported_course_code:PAGE161" not in result[
        "invented_academic_information"
    ]


def test_negated_non_authority_claim_is_not_graded_as_positive_authority() -> None:
    result = grade_turn(
        case={
            "id": "eligibility_en",
            "kind": "eligibility",
            "expected_tool": "check_course_eligibility",
        },
        response=_eligibility_response(
            "The modeled result is eligible, but the data is NOT fully authoritative."
        ),
        initial_tool_calls=[_eligibility_call()],
        known_course_codes=["CSE221"],
    )

    assert "non_authoritative_result_requires_manual_review" not in result["reasons"]


def test_arabic_prose_with_technical_terms_and_course_codes_is_arabic() -> None:
    assert detect_language("يمكنك تسجيل CSE221 مع human review في page161.") == "ar"
    assert detect_language("You can take CSE221 ويمكنك التسجيل.") == "mixed"


def test_multi_tool_execution_history_is_recorded_and_review_is_aggregated() -> None:
    eligibility_result = {
        "course": {"code": "CSE221"},
        "decision": "ELIGIBLE",
        "status": "ELIGIBLE",
        "eligible": True,
        "authoritative": False,
        "requires_human_review": False,
    }
    audit_result = {
        "status": "INDETERMINATE",
        "requirement_set_status": "INCOMPLETE",
        "credits": {"completed": 84, "required": 144, "remaining": 60},
        "requirements": {"satisfied_count": 1, "total_count": 3},
        "requires_human_review": True,
    }
    response = AdvisorResponse(
        text="CSE221 is eligible in the modeled result; the degree audit is indeterminate and requires human review.",
        requires_human_review=True,
        tool_executions=[
            AdvisorToolExecution(
                call_id="call-1",
                tool_name="check_course_eligibility",
                arguments={"course_code": "CSE221"},
                status="executed",
                round_index=1,
                result=eligibility_result,
            ),
            AdvisorToolExecution(
                call_id="call-2",
                tool_name="degree_audit",
                arguments={},
                status="executed",
                round_index=2,
                result=audit_result,
            ),
        ],
    )

    result = grade_turn(
        case={
            "id": "compound",
            "kind": "compound",
            "required_tools": ["check_course_eligibility", "degree_audit"],
        },
        response=response,
        initial_tool_calls=[_eligibility_call()],
        tool_calls_by_round=[
            [_eligibility_call()],
            [ToolCall(name="degree_audit", arguments={})],
        ],
        known_course_codes=["CSE221"],
    )

    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert result["tool_execution_count"] == 2
    assert result["tool_round_count"] == 2
    assert result["human_review_required"] is True
    assert result["human_review_preserved"] is True
    assert result["selected_tools"] == ["check_course_eligibility", "degree_audit"]
    assert len(result["trusted_tool_summaries"]) == 2


def test_repeated_tool_execution_is_a_hard_failure() -> None:
    response = AdvisorResponse(
        text="The first result is retained.",
        tool_executions=[
            AdvisorToolExecution(
                call_id="call-1",
                tool_name="check_course_eligibility",
                arguments={"course_code": "CSE221"},
                status="executed",
                round_index=1,
                result=_eligibility_response("unused").tool_result,
            ),
            AdvisorToolExecution(
                call_id="call-2",
                tool_name="check_course_eligibility",
                arguments={"course_code": "CSE221"},
                status="rejected",
                round_index=2,
                result={
                    "error": {
                        "code": "REPEATED_TOOL_CALL",
                        "message": "repeated",
                    }
                },
            ),
        ],
    )

    result = grade_turn(
        case={"id": "eligibility_en", "expected_tool": "check_course_eligibility"},
        response=response,
        initial_tool_calls=[_eligibility_call()],
        tool_calls_by_round=[[_eligibility_call()], [_eligibility_call()]],
        known_course_codes=["CSE221"],
    )

    assert result["status"] == "FAIL"
    assert "tool_execution_bound_exceeded" in result["reasons"]
    assert len(result["rejected_tool_calls"]) == 1


def test_irrelevant_extra_tool_is_manual_review_not_automatic_pass() -> None:
    eligibility_result = _eligibility_response("unused").tool_result
    assert eligibility_result is not None
    response = AdvisorResponse(
        text="The eligibility result is available.",
        tool_executions=[
            AdvisorToolExecution(
                call_id="call-1",
                tool_name="check_course_eligibility",
                arguments={"course_code": "CSE221"},
                status="executed",
                round_index=1,
                result=eligibility_result,
            ),
            AdvisorToolExecution(
                call_id="call-2",
                tool_name="degree_audit",
                arguments={},
                status="executed",
                round_index=1,
                result={
                    "status": "ACADEMIC_REQUIREMENTS_NOT_SATISFIED",
                    "requirement_set_status": "COMPLETE",
                    "credits": {"completed": 84, "required": 144, "remaining": 60},
                    "requirements": {"satisfied_count": 1, "total_count": 3},
                    "requires_human_review": False,
                },
            ),
        ],
    )

    result = grade_turn(
        case={"id": "eligibility_en", "expected_tool": "check_course_eligibility"},
        response=response,
        initial_tool_calls=[_eligibility_call()],
        tool_calls_by_round=[
            [
                _eligibility_call(),
                ToolCall(name="degree_audit", arguments={}),
            ]
        ],
        known_course_codes=["CSE221"],
    )

    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert "unjustified_extra_tool_call" in result["reasons"]


def test_zero_evidence_retrieval_is_not_graded_as_supported() -> None:
    response = AdvisorResponse(
        text="No official evidence was returned, so I cannot confirm the rule.",
        tool_name="search_official_documents",
        tool_result={"results": []},
    )

    result = grade_turn(
        case={
            "id": "official_regulation",
            "kind": "official_documents",
            "expected_tool": "search_official_documents",
        },
        response=response,
        initial_tool_calls=[
            ToolCall(
                name="search_official_documents",
                arguments={"query": "registration"},
            )
        ],
    )

    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert result["citations_supported"] is None
    assert "retrieval_no_evidence" in result["reasons"]


def test_degree_audit_rule_page_mismatch_is_a_hard_failure() -> None:
    result = grade_turn(
        case={"id": "degree_audit", "kind": "degree_audit", "expected_tool": "degree_audit"},
        response=AdvisorResponse(
            text="REQ23-004 is satisfied according to page 81.",
            requires_human_review=False,
            tool_executions=[
                AdvisorToolExecution(
                    call_id="call-1",
                    tool_name="degree_audit",
                    arguments={},
                    status="executed",
                    round_index=1,
                    result={
                        "status": "ACADEMIC_REQUIREMENTS_NOT_SATISFIED",
                        "requirement_set_status": "COMPLETE",
                        "credits": {"completed": 84, "required": 144, "remaining": 60},
                        "requirements": {"satisfied_count": 1, "total_count": 3},
                        "requires_human_review": False,
                        "citations": [
                            {"rule_id": "REQ23-004", "source_id": "SRC-RULES", "page": 13}
                        ],
                    },
                )
            ],
        ),
        initial_tool_calls=[ToolCall(name="degree_audit", arguments={})],
    )

    assert result["status"] == "FAIL"
    assert "degree_audit_deterministic_contradiction" in result["reasons"]


def test_degree_audit_numeric_summary_mismatch_is_a_hard_failure() -> None:
    result = grade_turn(
        case={"id": "degree_audit", "kind": "degree_audit", "expected_tool": "degree_audit"},
        response=AdvisorResponse(
            text="Completed credits: 85; required credits: 144; remaining credits: 59.",
            tool_name="degree_audit",
            tool_result={
                "status": "ACADEMIC_REQUIREMENTS_NOT_SATISFIED",
                "requirement_set_status": "COMPLETE",
                "credits": {"completed": 84, "required": 144, "remaining": 60},
                "requirements": {"satisfied_count": 1, "total_count": 3},
                "requires_human_review": False,
            },
        ),
        initial_tool_calls=[ToolCall(name="degree_audit", arguments={})],
    )

    assert result["status"] == "FAIL"
    assert "degree_audit_deterministic_contradiction" in result["reasons"]
