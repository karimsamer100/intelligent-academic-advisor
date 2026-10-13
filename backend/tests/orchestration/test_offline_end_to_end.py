from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.llm.contracts import GenerationRequest, GenerationResponse, ToolCall
from app.llm.errors import ProviderUnavailableError
from app.orchestration.composition import (
    AdvisorApplication,
    AdvisorStaticDependencies,
    build_advisor_application,
    build_advisor_static_dependencies,
)
from app.orchestration.contracts import AdvisorRequest
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService


class ScriptedProvider:
    """Offline provider script used to exercise the real advisor composition."""

    def __init__(
        self,
        responses: list[GenerationResponse] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._responses = list(responses or [])
        self._error = error
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        if not self._responses:
            raise AssertionError("the scripted provider ran out of responses")
        return self._responses.pop(0)

    def generate_structured(
        self,
        request: GenerationRequest,
        response_model: type[BaseModel],
    ) -> BaseModel:
        del request, response_model
        raise AssertionError("structured generation is not part of this suite")


class EmptyRetriever:
    def search(self, request: Any) -> list[Any]:
        del request
        return []


class FailingRetriever:
    def search(self, request: Any) -> list[Any]:
        del request
        raise RuntimeError("offline retriever failure")


@pytest.fixture(scope="module")
def static_dependencies() -> AdvisorStaticDependencies:
    root = Path(__file__).resolve().parents[3]
    settings = Settings(
        _env_file=None,
        academic_data_foundation_path=root / "data" / "academic_foundation",
        student_data_path=root / "data" / "students" / "students.json",
    )
    return build_advisor_static_dependencies(settings)


def _call(
    name: str,
    arguments: dict[str, Any],
    call_id: str,
) -> ToolCall:
    return ToolCall(call_id=call_id, name=name, arguments=arguments)


def _application(
    static: AdvisorStaticDependencies,
    provider: ScriptedProvider,
    *,
    rag_service: RAGService | None = None,
) -> AdvisorApplication:
    return build_advisor_application(
        llm_service=LLMService(provider),
        planning_service=static.planning_service,
        rag_service=rag_service or RAGService(EmptyRetriever()),
        student_repository=static.student_repository,
        academic_data=static.academic_data,
    )


def _respond(
    static: AdvisorStaticDependencies,
    provider: ScriptedProvider,
    message: str,
    *,
    rag_service: RAGService | None = None,
):
    return _application(static, provider, rag_service=rag_service).orchestrator.respond(
        AdvisorRequest(user_message=message, student_id="DEV-STUDENT-001")
    )


def test_real_composition_course_information_preserves_expression_and_unknown_corequisites(
    static_dependencies: AdvisorStaticDependencies,
) -> None:
    provider = ScriptedProvider(
        [
            GenerationResponse(
                tool_calls=[
                    _call(
                        "get_course_information",
                        {"course_code": "CSE221"},
                        "course-1",
                    )
                ]
            ),
            GenerationResponse(
                content="The structured course information is available."
            ),
        ]
    )

    response = _respond(
        static_dependencies,
        provider,
        "What are the prerequisites and corequisites for CSE221?",
    )

    assert response.academic_facts.course_information[0].course["identity"] == (
        "R23:CAIE:CSE221"
    )
    expression = response.academic_facts.course_information[0].prerequisites[
        "expression"
    ]
    assert expression["type"] == "AND"
    assert [child["course_code"] for child in expression["children"]] == [
        "CSE141",
        "CSE121",
    ]
    assert response.academic_facts.course_information[0].coverage["corequisites"] == (
        "UNAVAILABLE"
    )


def test_real_composition_keeps_eligibility_and_course_facts_separate(
    static_dependencies: AdvisorStaticDependencies,
) -> None:
    provider = ScriptedProvider(
        [
            GenerationResponse(
                tool_calls=[
                    _call(
                        "check_course_eligibility",
                        {"course_code": "CSE221"},
                        "eligibility-1",
                    ),
                    _call(
                        "get_course_information",
                        {"course_code": "CSE221"},
                        "course-1",
                    ),
                ]
            ),
            GenerationResponse(
                content=(
                    "The modeled eligibility result is ELIGIBLE and the structured "
                    "course facts contain the direct prerequisites."
                )
            ),
        ]
    )

    response = _respond(
        static_dependencies,
        provider,
        "Can I take CSE221 and what prerequisites does it have?",
    )

    assert response.grounding.status == "GROUNDED"
    assert response.academic_facts.eligibility[0].decision == "ELIGIBLE"
    assert response.academic_facts.eligibility[0].authoritative is False
    assert response.academic_facts.course_information[0].prerequisites["expression"][
        "type"
    ] == "AND"
    assert {
        (item.call_id, item.authoritative, item.requires_human_review)
        for item in response.academic_facts.authority
    } == {
        ("eligibility-1", False, False),
        ("course-1", False, None),
    }


def test_real_composition_degree_audit_keeps_bounded_progress_and_review_facts(
    static_dependencies: AdvisorStaticDependencies,
) -> None:
    provider = ScriptedProvider(
        [
            GenerationResponse(
                tool_calls=[_call("degree_audit", {}, "audit-1")]
            ),
            GenerationResponse(content="The modeled degree audit is available."),
        ]
    )

    response = _respond(
        static_dependencies,
        provider,
        "Run my degree audit and show my progress.",
    )

    audit = response.academic_facts.degree_audit[0]
    assert audit.credits["completed"] == response.tool_result["credits"]["completed"]
    assert audit.requirements.total_count == response.tool_result["requirements"][
        "total_count"
    ]
    assert all(detail.id for detail in audit.requirements.details)
    assert audit.authoritative is False
    assert audit.requires_human_review is True
    assert response.academic_facts.eligibility == []


def test_real_composition_empty_rag_is_explicitly_no_evidence(
    static_dependencies: AdvisorStaticDependencies,
) -> None:
    provider = ScriptedProvider(
        [
            GenerationResponse(
                tool_calls=[
                    _call(
                        "search_official_documents",
                        {"query": "registration deadlines"},
                        "rag-1",
                    )
                ]
            ),
            GenerationResponse(
                content="No official document evidence was returned for this policy question."
            ),
        ]
    )

    response = _respond(
        static_dependencies,
        provider,
        "What does the regulation say about registration deadlines?",
    )

    documents = response.academic_facts.official_documents[0]
    assert documents.coverage_status == "NO_EVIDENCE"
    assert documents.evidence_available is False
    assert response.academic_facts.eligibility == []
    assert response.academic_facts.course_information == []
    assert response.grounding.status == "GROUNDED"


def test_real_composition_compound_planning_and_rag_results_keep_review_boundaries(
    static_dependencies: AdvisorStaticDependencies,
) -> None:
    provider = ScriptedProvider(
        [
            GenerationResponse(
                tool_calls=[
                    _call(
                        "check_course_eligibility",
                        {"course_code": "CSE221"},
                        "eligibility-1",
                    ),
                    _call("degree_audit", {}, "audit-1"),
                    _call(
                        "search_official_documents",
                        {"query": "registration policy"},
                        "rag-1",
                    ),
                ]
            ),
            GenerationResponse(
                content=(
                    "Eligibility is ELIGIBLE. The degree audit requires human review. "
                    "The policy search returned no evidence."
                )
            ),
        ]
    )

    response = _respond(
        static_dependencies,
        provider,
        "Check eligibility, audit my degree, and find the registration policy.",
    )

    authority = {item.call_id: item for item in response.academic_facts.authority}
    assert authority["eligibility-1"].requires_human_review is False
    assert authority["audit-1"].requires_human_review is True
    assert authority["rag-1"].requires_human_review is None
    assert response.requires_human_review is True
    assert response.academic_facts.official_documents[0].coverage_status == (
        "NO_EVIDENCE"
    )


def test_real_composition_sequential_rounds_count_only_tool_generations(
    static_dependencies: AdvisorStaticDependencies,
) -> None:
    provider = ScriptedProvider(
        [
            GenerationResponse(
                tool_calls=[
                    _call(
                        "check_course_eligibility",
                        {"course_code": "CSE221"},
                        "eligibility-1",
                    )
                ]
            ),
            GenerationResponse(
                tool_calls=[
                    _call(
                        "get_course_information",
                        {"course_code": "CSE221"},
                        "course-1",
                    )
                ]
            ),
            GenerationResponse(content="Both modeled Planning results are available."),
        ]
    )

    response = _respond(
        static_dependencies,
        provider,
        "Check my eligibility and give me the course facts.",
    )

    assert len(provider.requests) == 3
    assert [record.round_index for record in response.tool_executions] == [1, 2]
    assert len(response.academic_facts.eligibility) == 1
    assert len(response.academic_facts.course_information) == 1


def test_real_composition_partial_tool_failure_keeps_successful_planning_facts(
    static_dependencies: AdvisorStaticDependencies,
) -> None:
    provider = ScriptedProvider(
        [
            GenerationResponse(
                tool_calls=[
                    _call(
                        "check_course_eligibility",
                        {"course_code": "CSE221"},
                        "eligibility-1",
                    ),
                    _call(
                        "search_official_documents",
                        {"query": "registration policy"},
                        "rag-1",
                    ),
                ]
            ),
            GenerationResponse(
                content="Eligibility is ELIGIBLE; the document search was unavailable."
            ),
        ]
    )

    response = _respond(
        static_dependencies,
        provider,
        "Check eligibility and search the policy.",
        rag_service=RAGService(FailingRetriever()),
    )

    assert len(response.academic_facts.eligibility) == 1
    assert response.academic_facts.official_documents == []
    assert [record.status for record in response.tool_executions] == [
        "executed",
        "failed",
    ]


def test_real_composition_provider_failure_has_no_fabricated_academic_facts(
    static_dependencies: AdvisorStaticDependencies,
) -> None:
    provider = ScriptedProvider(error=ProviderUnavailableError())

    response = _respond(
        static_dependencies,
        provider,
        "Can I take CSE221?",
    )

    assert response.academic_facts.model_dump(mode="json") == {
        "eligibility": [],
        "course_information": [],
        "degree_audit": [],
        "official_documents": [],
        "authority": [],
    }
    assert response.grounding.status == "NO_TRUSTED_FACTS"
    assert response.tool_executions == []


def test_real_composition_trusted_context_override_is_rejected_without_planning_facts(
    static_dependencies: AdvisorStaticDependencies,
) -> None:
    provider = ScriptedProvider(
        [
            GenerationResponse(
                tool_calls=[
                    _call(
                        "check_course_eligibility",
                        {
                            "course_code": "CSE221",
                            "student_id": "FORGED",
                            "regulation": 2018,
                            "program": "FORGED",
                            "gpa": 4.0,
                        },
                        "forged-1",
                    )
                ]
            )
        ]
    )

    response = _respond(
        static_dependencies,
        provider,
        "Use my supplied academic identity instead.",
    )

    assert response.tool_executions[0].status == "rejected"
    assert response.tool_result == {
        "error": {
            "code": "INVALID_TOOL_ARGUMENTS",
            "message": "The academic request contained invalid tool arguments.",
        }
    }
    assert response.academic_facts.eligibility == []
