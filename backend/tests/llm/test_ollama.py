from __future__ import annotations

import json
from contextlib import contextmanager
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.llm.contracts import (
    GenerationRequest,
    LLMMessage,
    MessageRole,
    ToolCall,
    ToolDefinition,
)
from app.llm.errors import (
    InvalidProviderResponseError,
    ProviderExecutionError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    StructuredOutputValidationError,
)
from app.llm.providers.ollama import OllamaProvider


class Requirement(BaseModel):
    code: str
    credits: int


class CoursePlan(BaseModel):
    title: str
    requirements: list[Requirement]


def _settings(**overrides: Any) -> Settings:
    values = {
        "llm_base_url": "http://ollama.test/",
        "llm_model": "qwen-test",
        "llm_timeout_seconds": 3.5,
        "llm_num_ctx": 8192,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@contextmanager
def _provider(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    settings: Settings | None = None,
) -> Iterator[OllamaProvider]:
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        yield OllamaProvider(settings=settings or _settings(), client=client)


def _text_response(
    *,
    content: str = "provider answer",
    model: str = "qwen-test",
    done_reason: str = "stop",
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "done_reason": done_reason,
            "message": {"role": "assistant", "content": content},
        },
    )


def _tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="search_documents",
        description="Search official academic documents",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    )


def _tool_call() -> ToolCall:
    return ToolCall(
        call_id="call-1",
        name="search_documents",
        arguments={"query": "credit load"},
    )


def test_simple_generation_maps_model_messages_and_non_streaming_request() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return _text_response()

    with _provider(handler) as provider:
        response = provider.generate(
            GenerationRequest(
                messages=[LLMMessage(role=MessageRole.USER, content="What is the rule?")]
            )
        )

    assert captured == {
        "url": "http://ollama.test/api/chat",
        "payload": {
            "model": "qwen-test",
            "messages": [{"role": "user", "content": "What is the rule?"}],
            "stream": False,
            "options": {"num_ctx": 8192},
        },
    }
    assert "think" not in captured["payload"]
    assert response.content == "provider answer"


def test_generation_includes_configured_context_size() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return _text_response()

    with _provider(handler, settings=_settings(llm_num_ctx=16384)) as provider:
        provider.generate(
            GenerationRequest(
                messages=[LLMMessage(role=MessageRole.USER, content="Hello")]
            )
        )

    assert captured["payload"]["options"]["num_ctx"] == 16384


def test_system_user_assistant_and_tool_name_messages_map_to_ollama_roles() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["messages"] = json.loads(request.content)["messages"]
        return _text_response()

    request = GenerationRequest(
        messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are an advisor."),
            LLMMessage(role=MessageRole.USER, content="Find the rule."),
            LLMMessage(role=MessageRole.ASSISTANT, content="I will search."),
            LLMMessage(
                role=MessageRole.TOOL,
                content='{"results": []}',
                tool_name="search_documents",
            ),
        ]
    )

    with _provider(handler) as provider:
        provider.generate(request)

    assert captured["messages"] == [
        {"role": "system", "content": "You are an advisor."},
        {"role": "user", "content": "Find the rule."},
        {"role": "assistant", "content": "I will search."},
        {"role": "tool", "content": '{"results": []}', "tool_name": "search_documents"},
    ]


def test_generation_controls_map_to_supported_ollama_options() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["options"] = json.loads(request.content)["options"]
        return _text_response()

    request = GenerationRequest(
        messages=[LLMMessage(role=MessageRole.USER, content="Find the rule.")],
        temperature=0.2,
        max_tokens=256,
    )

    with _provider(handler) as provider:
        provider.generate(request)

    assert captured["options"] == {
        "num_ctx": 8192,
        "temperature": 0.2,
        "num_predict": 256,
    }


def test_tool_definitions_map_to_ollama_function_tools() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["tools"] = json.loads(request.content)["tools"]
        return _text_response()

    request = GenerationRequest(
        messages=[LLMMessage(role=MessageRole.USER, content="Search the rules.")],
        tools=[_tool_definition()],
    )

    with _provider(handler) as provider:
        provider.generate(request)

    assert captured["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search_documents",
                "description": "Search official academic documents",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        }
    ]


def test_assistant_tool_calls_map_to_ollama_function_calls_without_synthetic_ids() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["tool_calls"] = json.loads(request.content)["messages"][0]["tool_calls"]
        return _text_response()

    request = GenerationRequest(
        messages=[LLMMessage(role=MessageRole.ASSISTANT, tool_calls=[_tool_call()])]
    )

    with _provider(handler) as provider:
        provider.generate(request)

    assert captured["tool_calls"] == [
        {
            "function": {
                "name": "search_documents",
                "arguments": {"query": "credit load"},
            }
        }
    ]


def test_tool_message_with_only_call_id_is_rejected_without_fabricating_a_name() -> None:
    request = GenerationRequest(
        messages=[
            LLMMessage(role=MessageRole.TOOL, content="tool output", tool_call_id="call-1")
        ]
    )

    with _provider(lambda _: _text_response()) as provider:
        with pytest.raises(InvalidProviderResponseError):
            provider.generate(request)


def test_text_response_maps_content_finish_reason_and_model() -> None:
    with _provider(lambda _: _text_response(model="qwen-custom", done_reason="length")) as provider:
        response = provider.generate(
            GenerationRequest(
                messages=[LLMMessage(role=MessageRole.USER, content="Explain this.")]
            )
        )

    assert response.content == "provider answer"
    assert response.tool_calls == []
    assert response.finish_reason == "length"
    assert response.model == "qwen-custom"


def test_tool_call_response_maps_name_and_structured_arguments_without_id() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "qwen-test",
                "done_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search_documents",
                                "arguments": {"query": "credit load"},
                            }
                        }
                    ],
                },
            },
        )

    with _provider(handler) as provider:
        response = provider.generate(
            GenerationRequest(
                messages=[LLMMessage(role=MessageRole.USER, content="Search the rules.")]
            )
        )

    assert response.content == ""
    assert response.tool_calls == [
        ToolCall(
            call_id=None,
            name="search_documents",
            arguments={"query": "credit load"},
        )
    ]
    assert response.tool_calls[0].call_id is None


def test_response_can_contain_content_and_tool_calls() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "qwen-test",
                "done_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "I found a relevant rule.",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search_documents",
                                "arguments": {"query": "credit load"},
                            }
                        }
                    ],
                },
            },
        )

    with _provider(handler) as provider:
        response = provider.generate(
            GenerationRequest(
                messages=[LLMMessage(role=MessageRole.USER, content="Search the rules.")]
            )
        )

    assert response.content == "I found a relevant rule."
    assert response.tool_calls[0].name == "search_documents"


def test_malformed_successful_json_raises_safe_invalid_response_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    with _provider(handler) as provider:
        with pytest.raises(InvalidProviderResponseError) as raised:
            provider.generate(
                GenerationRequest(
                    messages=[LLMMessage(role=MessageRole.USER, content="Hello")]
                )
            )

    assert str(raised.value) == "LLM provider returned an invalid response"
    assert "not-json" not in str(raised.value)


def test_malformed_successful_tool_call_payload_raises_invalid_response_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "search_documents", "arguments": []}}
                    ],
                }
            },
        )

    with _provider(handler) as provider:
        with pytest.raises(InvalidProviderResponseError):
            provider.generate(
                GenerationRequest(
                    messages=[LLMMessage(role=MessageRole.USER, content="Hello")]
                )
            )


def test_connection_failure_maps_to_provider_unavailable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private connection details", request=request)

    with _provider(handler) as provider:
        with pytest.raises(ProviderUnavailableError) as raised:
            provider.generate(
                GenerationRequest(
                    messages=[LLMMessage(role=MessageRole.USER, content="Hello")]
                )
            )

    assert str(raised.value) == "LLM provider is unavailable"
    assert "private connection details" not in str(raised.value)


def test_other_httpx_request_error_maps_to_provider_execution_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("private read details", request=request)

    with _provider(handler) as provider:
        with pytest.raises(ProviderExecutionError):
            provider.generate(
                GenerationRequest(
                    messages=[LLMMessage(role=MessageRole.USER, content="Hello")]
                )
            )


def test_timeout_maps_to_provider_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private timeout details", request=request)

    with _provider(handler) as provider:
        with pytest.raises(ProviderTimeoutError):
            provider.generate(
                GenerationRequest(
                    messages=[LLMMessage(role=MessageRole.USER, content="Hello")]
                )
            )


def test_non_success_http_response_maps_to_provider_execution_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "private server details"})

    with _provider(handler) as provider:
        with pytest.raises(ProviderExecutionError) as raised:
            provider.generate(
                GenerationRequest(
                    messages=[LLMMessage(role=MessageRole.USER, content="Hello")]
                )
            )

    assert str(raised.value) == "LLM provider execution failed"
    assert "private server details" not in str(raised.value)


def test_settings_supply_ollama_base_url_model_and_positive_timeout() -> None:
    settings = _settings(
        llm_base_url="http://custom-ollama.test/",
        llm_model="custom-model",
        llm_timeout_seconds=12.5,
    )
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["model"] = json.loads(request.content)["model"]
        return _text_response()

    with _provider(handler, settings=settings) as provider:
        provider.generate(
            GenerationRequest(
                messages=[LLMMessage(role=MessageRole.USER, content="Hello")]
            )
        )

    assert settings.llm_timeout_seconds == pytest.approx(12.5)
    assert captured == {
        "url": "http://custom-ollama.test/api/chat",
        "model": "custom-model",
    }


def test_timeout_configuration_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _settings(llm_timeout_seconds=0)


def test_structured_generation_sends_response_model_schema_and_returns_nested_model() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return _text_response(
            content=json.dumps(
                {
                    "title": "Computer Science plan",
                    "requirements": [{"code": "CS101", "credits": 3}],
                }
            )
        )

    request = GenerationRequest(
        messages=[LLMMessage(role=MessageRole.USER, content="Build a plan.")]
    )

    with _provider(handler) as provider:
        result = provider.generate_structured(request, CoursePlan)

    assert captured["payload"]["format"] == CoursePlan.model_json_schema()
    assert captured["payload"]["think"] is False
    assert captured["payload"]["stream"] is False
    assert result == CoursePlan(
        title="Computer Science plan",
        requirements=[Requirement(code="CS101", credits=3)],
    )
    assert isinstance(result, CoursePlan)


def test_structured_generation_rejects_malformed_json_as_invalid_provider_response() -> None:
    with _provider(lambda _: _text_response(content="not-json")) as provider:
        with pytest.raises(InvalidProviderResponseError) as raised:
            provider.generate_structured(
                GenerationRequest(
                    messages=[LLMMessage(role=MessageRole.USER, content="Build a plan.")]
                ),
                CoursePlan,
            )

    assert str(raised.value) == "LLM provider returned an invalid response"
    assert "not-json" not in str(raised.value)


def test_structured_generation_rejects_valid_json_with_schema_errors() -> None:
    invalid_content = json.dumps(
        {
            "title": "Computer Science plan",
            "requirements": [{"code": "CS101", "credits": "three"}],
        }
    )

    with _provider(lambda _: _text_response(content=invalid_content)) as provider:
        with pytest.raises(StructuredOutputValidationError) as raised:
            provider.generate_structured(
                GenerationRequest(
                    messages=[LLMMessage(role=MessageRole.USER, content="Build a plan.")]
                ),
                CoursePlan,
            )

    assert str(raised.value) == "LLM structured output failed schema validation"
    assert "three" not in str(raised.value)


@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        ("connection", ProviderUnavailableError),
        ("timeout", ProviderTimeoutError),
        ("http", ProviderExecutionError),
    ],
)
def test_structured_generation_preserves_provider_error_mapping(
    failure: str,
    expected_error: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "connection":
            raise httpx.ConnectError("private connection details", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private timeout details", request=request)
        return httpx.Response(503, json={"error": "private server details"})

    with _provider(handler) as provider:
        with pytest.raises(expected_error):
            provider.generate_structured(
                GenerationRequest(
                    messages=[LLMMessage(role=MessageRole.USER, content="Build a plan.")]
                ),
                CoursePlan,
            )
