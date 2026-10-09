from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.llm.contracts import (
    GenerationRequest,
    GenerationResponse,
    MessageRole,
    ToolCall,
)
from app.llm.errors import ProviderTimeoutError, ProviderUnavailableError
from app.services.llm_service import LLMService
from app.tools.context import ToolExecutionContext
from app.tools.errors import ToolDataUnavailableError
from app.tools.interface import AcademicTool
from app.tools.registry import ToolRegistry
from app.orchestration.contracts import AdvisorRequest
from app.orchestration.orchestrator import AdvisorOrchestrator


class EligibilityArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    course_code: str = Field(min_length=1)


class AuditArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1)
    document_types: list[str] | None = None


class RecordingEligibilityTool(AcademicTool[EligibilityArguments]):
    name = "check_course_eligibility"
    description = "Check one course against trusted academic state."
    arguments_model = EligibilityArguments

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[EligibilityArguments, ToolExecutionContext]] = []
        self.payload = payload or {
            "course": {"code": "CSE341"},
            "decision": "ELIGIBLE",
            "requires_human_review": False,
        }

    def _execute(
        self,
        arguments: EligibilityArguments,
        trusted_context: ToolExecutionContext,
    ) -> dict[str, Any]:
        self.calls.append((arguments, trusted_context))
        return self.payload


class RecordingAuditTool(AcademicTool[AuditArguments]):
    name = "degree_audit"
    description = "Audit the trusted student's modeled degree requirements."
    arguments_model = AuditArguments

    def __init__(self) -> None:
        self.calls: list[ToolExecutionContext] = []

    def _execute(
        self,
        arguments: AuditArguments,
        trusted_context: ToolExecutionContext,
    ) -> dict[str, Any]:
        del arguments
        self.calls.append(trusted_context)
        return {
            "status": "INDETERMINATE",
            "credits": {"completed": 84, "remaining": 60},
            "requires_human_review": True,
        }


class RecordingSearchTool(AcademicTool[SearchArguments]):
    name = "search_official_documents"
    description = "Search official academic documents for evidence."
    arguments_model = SearchArguments

    def __init__(self) -> None:
        self.calls: list[tuple[SearchArguments, ToolExecutionContext]] = []

    def _execute(
        self,
        arguments: SearchArguments,
        trusted_context: ToolExecutionContext,
    ) -> dict[str, Any]:
        self.calls.append((arguments, trusted_context))
        return {
            "results": [
                {
                    "text": "The maximum registered load is defined by the regulation.",
                    "source_id": "SRC-BYLAW-2023",
                    "page_start": 42,
                }
            ],
            "citations": [
                {"source_id": "SRC-BYLAW-2023", "page": 42},
            ],
            "requires_human_review": False,
        }


class UnavailableEligibilityTool(RecordingEligibilityTool):
    def _execute(
        self,
        arguments: EligibilityArguments,
        trusted_context: ToolExecutionContext,
    ) -> dict[str, Any]:
        del arguments, trusted_context
        raise ToolDataUnavailableError(self.name)


class QueueProvider:
    def __init__(
        self,
        responses: list[GenerationResponse] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if not self.responses:
            raise AssertionError("the fake provider ran out of responses")
        return self.responses.pop(0)

    def generate_structured(
        self,
        request: GenerationRequest,
        response_model: type[BaseModel],
    ) -> BaseModel:
        raise AssertionError("structured generation is not part of orchestration")


def _registry(
    eligibility: RecordingEligibilityTool | None = None,
) -> tuple[ToolRegistry, RecordingEligibilityTool, RecordingAuditTool, RecordingSearchTool]:
    eligibility_tool = eligibility or RecordingEligibilityTool()
    audit_tool = RecordingAuditTool()
    search_tool = RecordingSearchTool()
    return (
        ToolRegistry([eligibility_tool, audit_tool, search_tool]),
        eligibility_tool,
        audit_tool,
        search_tool,
    )


def _orchestrator(
    provider: QueueProvider,
    registry: ToolRegistry,
) -> AdvisorOrchestrator:
    return AdvisorOrchestrator(LLMService(provider), registry)


def _request(message: str = "Can I take CSE341?") -> AdvisorRequest:
    return AdvisorRequest(user_message=message, student_id="student-001")


def _tool_call(
    name: str = "check_course_eligibility",
    arguments: dict[str, Any] | None = None,
    call_id: str | None = "call-1",
) -> ToolCall:
    return ToolCall(
        call_id=call_id,
        name=name,
        arguments=(
            arguments if arguments is not None else {"course_code": "CSE341"}
        ),
    )


def test_no_tool_response_is_returned_directly() -> None:
    provider = QueueProvider([GenerationResponse(content="Hello! I can help with advising.")])
    registry, *_ = _registry()

    response = _orchestrator(provider, registry).respond(_request("Hello"))

    assert response.text == "Hello! I can help with advising."
    assert response.tool_name is None
    assert response.tool_result is None
    assert response.requires_human_review is False
    assert len(provider.requests) == 1
    system_prompt = provider.requests[0].messages[0].content
    assert "advisor-system-v1" in system_prompt
    assert "INDETERMINATE" in system_prompt
    assert "requires_human_review=true" in system_prompt
    assert [definition.name for definition in provider.requests[0].tools] == [
        "check_course_eligibility",
        "degree_audit",
        "search_official_documents",
    ]


def test_eligibility_flow_executes_once_with_trusted_context_and_preserves_messages() -> None:
    call = _tool_call()
    provider = QueueProvider(
        [
            GenerationResponse(tool_calls=[call]),
            GenerationResponse(content="The trusted academic result says you may take CSE341."),
        ]
    )
    registry, eligibility, *_ = _registry()

    response = _orchestrator(provider, registry).respond(_request())

    assert response.text == "The trusted academic result says you may take CSE341."
    assert response.tool_name == "check_course_eligibility"
    assert response.tool_result == eligibility.payload
    assert eligibility.calls == [
        (
            EligibilityArguments(course_code="CSE341"),
            ToolExecutionContext(student_id="student-001"),
        )
    ]
    assert len(provider.requests) == 2

    final_messages = provider.requests[1].messages
    assert [message.role for message in final_messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assert final_messages[2].tool_calls == [call]
    assert final_messages[3].tool_call_id == "call-1"
    assert final_messages[3].tool_name == "check_course_eligibility"
    assert final_messages[3].content == json.dumps(
        eligibility.payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    assert provider.requests[1].tools == []


def test_degree_audit_flow_preserves_indeterminate_human_review_result() -> None:
    call = _tool_call("degree_audit", {})
    provider = QueueProvider(
        [
            GenerationResponse(tool_calls=[call]),
            GenerationResponse(content="The degree audit is indeterminate and needs review."),
        ]
    )
    registry, _, audit, _ = _registry()

    response = _orchestrator(provider, registry).respond(
        _request("How much of my degree have I completed?")
    )

    assert response.text == "The degree audit is indeterminate and needs review."
    assert response.tool_name == "degree_audit"
    assert response.tool_result == {
        "status": "INDETERMINATE",
        "credits": {"completed": 84, "remaining": 60},
        "requires_human_review": True,
    }
    assert response.requires_human_review is True
    assert audit.calls == [ToolExecutionContext(student_id="student-001")]


def test_official_document_flow_passes_evidence_and_citations_to_final_generation() -> None:
    call = _tool_call(
        "search_official_documents",
        {"query": "maximum registered credit hours", "document_types": ["REGULATION"]},
    )
    provider = QueueProvider(
        [
            GenerationResponse(tool_calls=[call]),
            GenerationResponse(content="The official evidence is on page 42."),
        ]
    )
    registry, _, _, search = _registry()

    response = _orchestrator(provider, registry).respond(
        _request("What does Regulation 2023 say about credit hours?")
    )

    assert response.text == "The official evidence is on page 42."
    assert response.tool_result is not None
    assert response.tool_result["citations"] == [
        {"source_id": "SRC-BYLAW-2023", "page": 42}
    ]
    assert search.calls[0][0] == SearchArguments(
        query="maximum registered credit hours",
        document_types=["REGULATION"],
    )
    assert "SRC-BYLAW-2023" in provider.requests[1].messages[3].content
    assert '"page":42' in provider.requests[1].messages[3].content


def test_multiple_initial_tool_calls_are_rejected_without_execution() -> None:
    provider = QueueProvider(
        [
            GenerationResponse(
                tool_calls=[
                    _tool_call(call_id="call-1"),
                    _tool_call("degree_audit", {}, call_id="call-2"),
                ]
            )
        ]
    )
    registry, eligibility, audit, search = _registry()

    response = _orchestrator(provider, registry).respond(_request())

    assert "multiple tool calls" in response.text.lower()
    assert response.tool_name is None
    assert response.tool_result is None
    assert eligibility.calls == []
    assert audit.calls == []
    assert search.calls == []
    assert len(provider.requests) == 1


def test_final_tool_call_is_rejected_and_the_tool_was_still_executed_only_once() -> None:
    first_call = _tool_call(call_id="call-1")
    repeated_call = _tool_call(call_id="call-2")
    provider = QueueProvider(
        [
            GenerationResponse(tool_calls=[first_call]),
            GenerationResponse(tool_calls=[repeated_call]),
        ]
    )
    registry, eligibility, *_ = _registry()

    response = _orchestrator(provider, registry).respond(_request())

    assert "additional tool call" in response.text.lower()
    assert response.tool_name == "check_course_eligibility"
    assert response.tool_result == eligibility.payload
    assert len(eligibility.calls) == 1
    assert len(provider.requests) == 2


def test_unknown_tool_returns_safe_failure_without_a_second_generation() -> None:
    provider = QueueProvider(
        [GenerationResponse(tool_calls=[_tool_call("unknown_tool")])]
    )
    registry, *_ = _registry()

    response = _orchestrator(provider, registry).respond(_request())

    assert "unknown tool" in response.text.lower()
    assert response.tool_name == "unknown_tool"
    assert response.tool_result == {
        "error": {
            "code": "UNKNOWN_TOOL",
            "message": "The requested tool is an unknown tool or unavailable.",
        }
    }
    assert len(provider.requests) == 1


def test_malformed_arguments_are_rejected_and_cannot_override_trusted_student_id() -> None:
    provider = QueueProvider(
        [
            GenerationResponse(
                tool_calls=[
                    _tool_call(
                        arguments={"course_code": "CSE341", "student_id": "forged"}
                    )
                ]
            )
        ]
    )
    registry, eligibility, *_ = _registry()

    response = _orchestrator(provider, registry).respond(_request())

    assert "invalid tool arguments" in response.text.lower()
    assert response.tool_result == {
        "error": {
            "code": "INVALID_TOOL_ARGUMENTS",
            "message": "The academic request contained invalid tool arguments.",
        }
    }
    assert eligibility.calls == []
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "provider_error, expected_text",
    [
        (ProviderTimeoutError(), "timed out"),
        (ProviderUnavailableError(), "unavailable"),
    ],
)
def test_provider_failures_return_safe_application_responses(
    provider_error: Exception,
    expected_text: str,
) -> None:
    provider = QueueProvider(error=provider_error)
    registry, *_ = _registry()

    response = _orchestrator(provider, registry).respond(_request())

    assert expected_text in response.text.lower()
    assert response.tool_name is None
    assert response.tool_result is None
    assert response.requires_human_review is False
    assert len(provider.requests) == 1


def test_tool_data_unavailable_does_not_produce_a_fabricated_success() -> None:
    provider = QueueProvider(
        [GenerationResponse(tool_calls=[_tool_call()])]
    )
    registry, unavailable, *_ = _registry(UnavailableEligibilityTool())

    response = _orchestrator(provider, registry).respond(_request())

    assert "academic data is unavailable" in response.text.lower()
    assert response.tool_name == unavailable.name
    assert response.tool_result == {
        "error": {
            "code": "TOOL_DATA_UNAVAILABLE",
            "message": "Required academic data is unavailable.",
        }
    }
    assert len(provider.requests) == 1
