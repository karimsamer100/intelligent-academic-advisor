from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.llm.contracts import (
    GenerationRequest,
    GenerationResponse,
    LLMMessage,
    MessageRole,
    ToolCall,
    ToolDefinition,
)


def _tool_call() -> ToolCall:
    return ToolCall(
        call_id="call-1",
        name="search_documents",
        arguments={"query": "credit load", "filters": {"year": 2023}},
    )


def _tool_definition(name: str = "search_documents") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="Search official academic documents",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    )


def test_valid_messages_cover_text_tool_call_and_tool_result_context() -> None:
    system = LLMMessage(role=MessageRole.SYSTEM, content="You are an advisor.")
    user = LLMMessage(role=MessageRole.USER, content="Can I take this course?")
    assistant = LLMMessage(role=MessageRole.ASSISTANT, content="I will check.")
    assistant_with_tool_call = LLMMessage(
        role=MessageRole.ASSISTANT,
        tool_calls=[_tool_call()],
    )
    tool = LLMMessage(
        role=MessageRole.TOOL,
        content='{"results": []}',
        tool_call_id="call-1",
    )

    assert system.role is MessageRole.SYSTEM
    assert user.content == "Can I take this course?"
    assert assistant.content == "I will check."
    assert assistant_with_tool_call.tool_calls[0].name == "search_documents"
    assert tool.tool_call_id == "call-1"


@pytest.mark.parametrize(
    ("role", "kwargs"),
    [
        (MessageRole.SYSTEM, {}),
        (MessageRole.USER, {"content": "   "}),
        (MessageRole.TOOL, {"content": "tool output"}),
        (MessageRole.ASSISTANT, {}),
    ],
)
def test_message_contracts_reject_missing_role_content(
    role: MessageRole,
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        LLMMessage(role=role, **kwargs)


def test_message_contracts_enforce_role_semantics() -> None:
    with pytest.raises(ValidationError):
        LLMMessage(role=MessageRole.USER, content="question", tool_calls=[_tool_call()])

    with pytest.raises(ValidationError):
        LLMMessage(role=MessageRole.ASSISTANT, content="answer", tool_call_id="call-1")

    with pytest.raises(ValidationError):
        LLMMessage(role=MessageRole.TOOL, content="tool output")

    with pytest.raises(ValidationError):
        LLMMessage(
            role=MessageRole.TOOL,
            content="tool output",
            tool_call_id="call-1",
            tool_calls=[_tool_call()],
        )


def test_generation_request_requires_messages() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest()


def test_generation_request_accepts_tools_and_minimal_controls() -> None:
    request = GenerationRequest(
        messages=[LLMMessage(role=MessageRole.USER, content="Find the rule.")],
        tools=[_tool_definition()],
        temperature=0.2,
        max_tokens=256,
    )

    assert request.tools[0].input_schema["type"] == "object"
    assert request.temperature == pytest.approx(0.2)
    assert request.max_tokens == 256


def test_generation_request_rejects_duplicate_tool_names() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(
            messages=[LLMMessage(role=MessageRole.USER, content="Find the rule.")],
            tools=[_tool_definition(), _tool_definition()],
        )


def test_tool_call_preserves_structured_arguments() -> None:
    call = _tool_call()

    assert call.call_id == "call-1"
    assert call.arguments == {
        "query": "credit load",
        "filters": {"year": 2023},
    }


def test_generation_response_accepts_text_only() -> None:
    response = GenerationResponse(content="The course is available.", finish_reason="stop")

    assert response.content == "The course is available."
    assert response.tool_calls == []


def test_generation_response_accepts_tool_calls_only() -> None:
    response = GenerationResponse(tool_calls=[_tool_call()], finish_reason="tool_calls")

    assert response.content is None
    assert response.tool_calls[0].call_id == "call-1"


def test_generation_response_accepts_text_and_tool_calls() -> None:
    response = GenerationResponse(
        content="I found a relevant rule.",
        tool_calls=[_tool_call()],
        model="local-model",
    )

    assert response.content == "I found a relevant rule."
    assert response.model == "local-model"


def test_generation_response_rejects_empty_content_and_tool_calls() -> None:
    with pytest.raises(ValidationError):
        GenerationResponse()
