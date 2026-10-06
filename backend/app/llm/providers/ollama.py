"""Ollama's native HTTP adapter for the provider-neutral LLM contract."""

from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.llm.contracts import (
    GenerationRequest,
    GenerationResponse,
    LLMMessage,
    MessageRole,
    ToolCall,
)
from app.llm.errors import (
    InvalidProviderResponseError,
    ProviderExecutionError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    StructuredOutputValidationError,
)

StructuredT = TypeVar("StructuredT", bound=BaseModel)


class OllamaProvider:
    """Concrete provider for Ollama's non-streaming ``/api/chat`` endpoint."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or httpx.Client(timeout=self._settings.llm_timeout_seconds)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate one response and translate provider failures safely."""

        return self._generate_response(request)

    def generate_structured(
        self,
        request: GenerationRequest,
        response_model: type[StructuredT],
    ) -> StructuredT:
        """Generate JSON using Ollama's schema format and validate it."""

        response = self._generate_response(
            request,
            response_format=response_model.model_json_schema(),
            think=False,
        )

        try:
            structured_payload = json.loads(response.content or "")
        except (TypeError, ValueError) as exc:
            raise InvalidProviderResponseError from exc

        try:
            return response_model.model_validate(structured_payload)
        except ValidationError as exc:
            raise StructuredOutputValidationError from exc

    def _generate_response(
        self,
        request: GenerationRequest,
        *,
        response_format: dict[str, Any] | None = None,
        think: bool | None = None,
    ) -> GenerationResponse:
        payload = self._build_request_payload(request)
        if response_format is not None:
            payload["format"] = response_format
        if think is not None:
            payload["think"] = think

        try:
            response = self._client.post(self._chat_url, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError from exc
        except httpx.RequestError as exc:
            raise ProviderExecutionError from exc
        except httpx.HTTPError as exc:
            raise ProviderExecutionError from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderExecutionError from exc

        try:
            response_payload = response.json()
        except ValueError as exc:
            raise InvalidProviderResponseError from exc

        return self._parse_response(response_payload)

    @property
    def _chat_url(self) -> str:
        return f"{self._settings.llm_base_url.rstrip('/')}/api/chat"

    def _build_request_payload(self, request: GenerationRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": [self._message_payload(message) for message in request.messages],
            "stream": False,
        }

        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in request.tools
            ]

        options: dict[str, Any] = {"num_ctx": self._settings.llm_num_ctx}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        payload["options"] = options

        return payload

    @staticmethod
    def _message_payload(message: LLMMessage) -> dict[str, Any]:
        if message.role is MessageRole.TOOL and message.tool_name is None:
            raise InvalidProviderResponseError

        payload: dict[str, Any] = {
            "role": message.role.value,
            "content": message.content or "",
        }

        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "function": {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    }
                }
                for tool_call in message.tool_calls
            ]

        if message.role is MessageRole.TOOL:
            payload["tool_name"] = message.tool_name

        return payload

    @classmethod
    def _parse_response(cls, payload: object) -> GenerationResponse:
        try:
            if not isinstance(payload, dict):
                raise TypeError

            message = payload.get("message")
            if not isinstance(message, dict):
                raise TypeError

            raw_tool_calls = message.get("tool_calls", [])
            if not isinstance(raw_tool_calls, list):
                raise TypeError

            tool_calls = [cls._parse_tool_call(raw_tool_call) for raw_tool_call in raw_tool_calls]
            return GenerationResponse(
                content=message.get("content"),
                tool_calls=tool_calls,
                finish_reason=payload.get("done_reason"),
                model=payload.get("model"),
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise InvalidProviderResponseError from exc

    @staticmethod
    def _parse_tool_call(payload: object) -> ToolCall:
        if not isinstance(payload, dict):
            raise TypeError

        function = payload.get("function")
        if not isinstance(function, dict):
            raise TypeError

        return ToolCall(
            call_id=payload.get("id"),
            name=function.get("name"),
            arguments=function.get("arguments"),
        )


__all__ = ["OllamaProvider"]
