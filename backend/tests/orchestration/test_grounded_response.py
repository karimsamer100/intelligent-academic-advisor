from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from app.orchestration.contracts import AdvisorResponse
from app.orchestration.facts import build_advisor_academic_facts
from app.orchestration.grounding import protect_advisor_text


def _eligibility_result(
    *,
    eligible: bool | None = True,
    authoritative: bool = False,
    requires_human_review: bool = False,
) -> dict[str, object]:
    return {
        "course": {"code": "CSE221", "name": "Data Structures"},
        "decision": "ELIGIBLE" if eligible is True else "INELIGIBLE",
        "status": "ELIGIBLE" if eligible is True else "NOT_ELIGIBLE",
        "eligible": eligible,
        "authoritative": authoritative,
        "requires_human_review": requires_human_review,
        "rule_set_status": "COMPLETE",
        "reasons": [],
        "warnings": [],
        "missing_requirements": [],
        "conditions": [],
        "citations": [
            {"source_id": "RULE-CSE221", "page": 161, "rule_id": "PR-CSE221"}
        ],
    }


def _course_information_result() -> dict[str, object]:
    expression = {
        "type": "AND",
        "children": [
            {"type": "COURSE_PASSED", "course_code": "CSE141"},
            {"type": "COURSE_PASSED", "course_code": "CSE121"},
        ],
    }
    return {
        "course": {
            "identity": "R23:CAIE:CSE221",
            "code": "CSE221",
            "name": "Data Structures",
            "credit_hours": 3,
            "regulation": "R23",
            "program": "CAIE",
            "approval_status": "SOURCE_VERIFIED",
            "verification_status": "SOURCE_VERIFIED",
        },
        "prerequisites": {
            "status": "COMPLETE",
            "rule_set_status": "COMPLETE",
            "reason_codes": [],
            "rules": [
                {
                    "rule_id": "PR-CSE221",
                    "expression": expression,
                    "approval_status": "SOURCE_VERIFIED",
                    "verification_status": "SOURCE_VERIFIED",
                    "critical_for_planner": True,
                    "provenance": {
                        "source_id": "RULE-CSE221",
                        "page": 161,
                        "rule_id": "PR-CSE221",
                    },
                }
            ],
            "expression": expression,
            "provenance": [
                {"source_id": "RULE-CSE221", "page": 161, "rule_id": "PR-CSE221"}
            ],
        },
        "corequisites": {
            "status": "UNAVAILABLE",
            "rules": [],
            "reason": "Corequisite coverage is unavailable.",
            "reason_codes": ["MISSING_REQUIRED_DATA"],
        },
        "coverage": {
            "course": "AVAILABLE",
            "prerequisites": "COMPLETE",
            "corequisites": "UNAVAILABLE",
        },
        "data_source": {
            "source_mode": "NORMALIZED_DEVELOPMENT",
            "dataset_version": {"value": "dev"},
        },
        "course_provenance": [
            {
                "source_id": "COURSE-CSE221",
                "page": 20,
                "approval_status": "SOURCE_VERIFIED",
                "verification_status": "SOURCE_VERIFIED",
            }
        ],
        "authoritative": False,
        "diagnostics": [],
    }


def _degree_audit_result() -> dict[str, object]:
    return {
        "status": "HUMAN_REVIEW_REQUIRED",
        "requirement_set_status": "INCOMPLETE",
        "authoritative": False,
        "requires_human_review": True,
        "reasons": ["MISSING_REQUIRED_DATA"],
        "credits": {"completed": 84, "required": 144, "remaining": 60},
        "requirements": {
            "satisfied_count": 2,
            "total_count": 4,
            "remaining_ids": ["REQ-003"],
            "review_ids": ["REQ-003"],
            "details": [
                {
                    "id": "REQ-003",
                    "type": "COURSE_COMPLETION",
                    "outcome": "INDETERMINATE",
                    "requires_human_review": True,
                    "reason_codes": ["MISSING_REQUIRED_DATA"],
                    "provenance": [
                        {"source_id": "AUDIT-REQ-003", "page": 84, "rule_id": "REQ-003"}
                    ],
                }
            ],
        },
        "mandatory_missing_courses": [],
        "elective_progress": [],
        "warnings": [],
        "citations": [{"source_id": "AUDIT-REQ-003", "page": 84}],
    }


def _execution(tool_name: str, call_id: str, result: dict[str, object], *, status: str = "executed"):
    return SimpleNamespace(
        tool_name=tool_name,
        call_id=call_id,
        status=status,
        result=result,
    )


def test_advisor_response_remains_backward_compatible_with_empty_fact_channels() -> None:
    response = AdvisorResponse(text="No tools were needed.")

    assert response.academic_facts.eligibility == []
    assert response.academic_facts.course_information == []
    assert response.academic_facts.degree_audit == []
    assert response.academic_facts.official_documents == []
    assert response.grounding.status == "NO_TRUSTED_FACTS"


def test_facts_preserve_per_tool_authority_and_review_semantics() -> None:
    facts = build_advisor_academic_facts(
        [
            _execution(
                "check_course_eligibility",
                "eligibility-1",
                _eligibility_result(
                    eligible=True,
                    authoritative=False,
                    requires_human_review=False,
                ),
            ),
            _execution("degree_audit", "audit-1", _degree_audit_result()),
            _execution(
                "search_official_documents",
                "rag-1",
                {"results": []},
            ),
        ]
    )

    assert facts.eligibility[0].decision == "ELIGIBLE"
    assert facts.eligibility[0].authoritative is False
    assert facts.eligibility[0].requires_human_review is False
    assert facts.degree_audit[0].status == "HUMAN_REVIEW_REQUIRED"
    assert facts.degree_audit[0].requires_human_review is True
    course_fact = build_advisor_academic_facts(
        [_execution("get_course_information", "course-1", _course_information_result())]
    ).course_information[0]
    assert course_fact.prerequisites["expression"]["type"] == "AND"
    assert course_fact.course["approval_status"] == "SOURCE_VERIFIED"
    assert course_fact.course_provenance[0].verification_status == "SOURCE_VERIFIED"
    assert facts.official_documents[0].evidence_available is False
    assert {
        authority.call_id: (
            authority.authoritative,
            authority.requires_human_review,
        )
        for authority in facts.authority
    } == {
        "eligibility-1": (False, False),
        "audit-1": (False, True),
        "rag-1": (None, None),
    }


def test_failed_tool_results_do_not_become_trusted_academic_facts() -> None:
    facts = build_advisor_academic_facts(
        [
            _execution(
                "check_course_eligibility",
                "failed-1",
                {"error": {"code": "TOOL_DATA_UNAVAILABLE"}},
                status="failed",
            )
        ]
    )

    assert facts.eligibility == []
    assert facts.authority == []


def test_partial_tool_failure_keeps_only_the_successful_fact() -> None:
    facts = build_advisor_academic_facts(
        [
            _execution(
                "degree_audit",
                "audit-failed",
                {"error": {"code": "TOOL_DATA_UNAVAILABLE"}},
                status="failed",
            ),
            _execution(
                "check_course_eligibility",
                "eligibility-1",
                _eligibility_result(),
            ),
        ]
    )

    assert len(facts.eligibility) == 1
    assert facts.degree_audit == []
    assert [item.call_id for item in facts.authority] == ["eligibility-1"]


def test_critical_eligibility_contradiction_uses_safe_fallback() -> None:
    facts = build_advisor_academic_facts(
        [_execution("check_course_eligibility", "eligibility-1", _eligibility_result())]
    )

    protected_text, assessment = protect_advisor_text(
        "You are not eligible to take CSE221.",
        facts,
    )

    assert assessment.status == "SAFE_FALLBACK"
    assert "ELIGIBLE" in protected_text
    assert protected_text != "You are not eligible to take CSE221."


def test_degree_audit_review_does_not_become_an_eligibility_review_flag() -> None:
    facts = build_advisor_academic_facts(
        [
            _execution("check_course_eligibility", "eligibility-1", _eligibility_result()),
            _execution("degree_audit", "audit-1", _degree_audit_result()),
        ]
    )

    _, assessment = protect_advisor_text(
        "Eligibility for CSE221 requires human review because the degree audit is incomplete.",
        facts,
    )

    assert assessment.status == "SAFE_FALLBACK"
    assert "ELIGIBILITY_REVIEW_FLAG_MISATTRIBUTED" in assessment.issues


def test_degree_audit_facts_keep_requirement_provenance_separate() -> None:
    facts = build_advisor_academic_facts(
        [_execution("degree_audit", "audit-1", _degree_audit_result())]
    )

    detail = facts.degree_audit[0].requirements.details[0]
    assert detail.id == "REQ-003"
    assert detail.requires_human_review is True
    assert detail.provenance[0].source_id == "AUDIT-REQ-003"
    assert detail.provenance[0].rule_id == "REQ-003"


def test_unknown_corequisites_are_not_rendered_as_confirmed_absence() -> None:
    facts = build_advisor_academic_facts(
        [_execution("get_course_information", "course-1", _course_information_result())]
    )

    protected_text, assessment = protect_advisor_text(
        "CSE221 has no corequisites.",
        facts,
    )

    assert assessment.status == "SAFE_FALLBACK"
    assert "UNAVAILABLE" in protected_text


def test_nested_and_or_not_expression_is_preserved_in_academic_facts() -> None:
    result = deepcopy(_course_information_result())
    nested_expression = {
        "type": "OR",
        "children": [
            {
                "type": "AND",
                "children": [
                    {"type": "COURSE_PASSED", "course_code": "CSE141"},
                    {"type": "COURSE_PASSED", "course_code": "CSE121"},
                ],
            },
            {
                "type": "NOT",
                "operand": {
                    "type": "COURSE_CURRENTLY_REGISTERED",
                    "course_code": "CSE221",
                },
            },
        ],
    }
    result["prerequisites"]["expression"] = nested_expression  # type: ignore[index]
    result["prerequisites"]["rules"][0]["expression"] = nested_expression  # type: ignore[index]

    facts = build_advisor_academic_facts(
        [_execution("get_course_information", "course-1", result)]
    )

    assert facts.course_information[0].prerequisites["expression"] == nested_expression


def test_incomplete_prerequisites_are_not_rendered_as_confirmed_absence() -> None:
    result = _course_information_result()
    result["prerequisites"] = {
        "status": "INCOMPLETE",
        "rule_set_status": "INCOMPLETE",
        "reason_codes": ["MISSING_REQUIRED_DATA"],
        "rules": [],
        "expression": None,
    }
    result["coverage"] = {
        "course": "AVAILABLE",
        "prerequisites": "INCOMPLETE",
        "corequisites": "UNAVAILABLE",
    }

    facts = build_advisor_academic_facts(
        [_execution("get_course_information", "course-1", result)]
    )
    _, assessment = protect_advisor_text("CSE221 has no prerequisites.", facts)

    assert assessment.status == "SAFE_FALLBACK"
    assert "UNAVAILABLE_PREREQUISITES_PRESENTED_AS_ABSENT" in assessment.issues


def test_course_credit_hours_are_not_replaced_by_an_unsupported_number() -> None:
    facts = build_advisor_academic_facts(
        [_execution("get_course_information", "course-1", _course_information_result())]
    )

    _, assessment = protect_advisor_text("CSE221 has 4 credit hours.", facts)

    assert assessment.status == "SAFE_FALLBACK"
    assert "COURSE_CREDIT_HOURS_CONTRADICTION" in assessment.issues


def test_no_rag_evidence_cannot_be_used_to_claim_no_prerequisites() -> None:
    facts = build_advisor_academic_facts(
        [_execution("search_official_documents", "rag-1", {"results": []})]
    )

    protected_text, assessment = protect_advisor_text(
        "The documents show that CSE221 has no prerequisites.",
        facts,
    )

    assert assessment.status == "SAFE_FALLBACK"
    assert "not available" in protected_text


def test_unsupported_degree_numeric_claim_uses_safe_fallback() -> None:
    facts = build_advisor_academic_facts(
        [_execution("degree_audit", "audit-1", _degree_audit_result())]
    )

    _, assessment = protect_advisor_text(
        "The degree audit reports completed credits: 100.",
        facts,
    )

    assert assessment.status == "SAFE_FALLBACK"
    assert "DEGREE_AUDIT_NUMERIC_CONTRADICTION" in assessment.issues


def test_wrong_requirement_source_page_pair_is_rejected() -> None:
    facts = build_advisor_academic_facts(
        [_execution("degree_audit", "audit-1", _degree_audit_result())]
    )

    _, assessment = protect_advisor_text(
        "REQ-003 is supported by AUDIT-REQ-003 page 99.",
        facts,
    )

    assert assessment.status == "SAFE_FALLBACK"
    assert "CITATION_PAGE_MISMATCH" in assessment.issues
