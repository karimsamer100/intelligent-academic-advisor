"""Minimal one-tool orchestration for grounded advisor responses."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.llm.contracts import (
    GenerationRequest,
    GenerationResponse,
    LLMMessage,
    MessageRole,
)
from app.llm.errors import (
    InvalidProviderResponseError,
    LLMProviderError,
    ProviderExecutionError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.services.llm_service import LLMService
from app.tools.context import ToolExecutionContext
from app.tools.errors import (
    ToolArgumentValidationError,
    ToolContextRequiredError,
    ToolDataUnavailableError,
    ToolError,
    ToolExecutionError,
    UnknownToolError,
)
from app.tools.registry import ToolRegistry
from app.orchestration.contracts import AdvisorRequest, AdvisorResponse
from app.orchestration.prompts import ADVISOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class AdvisorOrchestrator:
    """Coordinate one LLM response and at most one trusted tool execution."""

    def __init__(
        self,
        llm_service: LLMService,
        tool_registry: ToolRegistry,
        *,
        system_prompt: str = ADVISOR_SYSTEM_PROMPT,
    ) -> None:
        if not isinstance(llm_service, LLMService):
            raise TypeError("llm_service must be an LLMService")
        if not isinstance(tool_registry, ToolRegistry):
            raise TypeError("tool_registry must be a ToolRegistry")
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("system_prompt must be non-empty")
        self._llm_service = llm_service
        self._tool_registry = tool_registry
        self._system_prompt = system_prompt

    def respond(self, request: AdvisorRequest) -> AdvisorResponse:
        """Return a direct answer or a final answer after one tool round."""

        if not isinstance(request, AdvisorRequest):
            raise TypeError("request must be an AdvisorRequest")

        initial_messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=self._system_prompt),
            LLMMessage(role=MessageRole.USER, content=request.user_message),
        ]
        initial_request = GenerationRequest(
            messages=initial_messages,
            tools=list(self._tool_registry.definitions),
        )

        try:
            initial_response = self._generate(initial_request)
        except LLMProviderError as exc:
            return self._provider_failure(exc)
        except Exception:
            logger.exception("unexpected advisor provider failure")
            return self._internal_failure()

        if not initial_response.tool_calls:
            return AdvisorResponse(text=initial_response.content or "")

        if len(initial_response.tool_calls) != 1:
            return AdvisorResponse(
                text="I could not safely process multiple tool calls in one request."
            )

        tool_call = initial_response.tool_calls[0]
        trusted_context = ToolExecutionContext(student_id=request.student_id)
        try:
            tool_result = self._tool_registry.execute(
                tool_call.name,
                tool_call.arguments,
                trusted_context,
            )
        except ToolError as exc:
            return self._tool_failure(tool_call.name, exc)
        except Exception:
            logger.exception(
                "unexpected advisor tool failure",
                extra={"tool_name": tool_call.name},
            )
            return self._tool_failure(tool_call.name, ToolExecutionError(tool_call.name))

        try:
            tool_message_content = json.dumps(
                tool_result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError):
            logger.exception(
                "advisor tool result could not be serialized",
                extra={"tool_name": tool_call.name},
            )
            return self._tool_failure(tool_call.name, ToolExecutionError(tool_call.name))

        assistant_tool_message = LLMMessage(
            role=MessageRole.ASSISTANT,
            content=initial_response.content,
            tool_calls=[tool_call],
        )
        tool_result_message = LLMMessage(
            role=MessageRole.TOOL,
            content=tool_message_content,
            tool_call_id=tool_call.call_id,
            tool_name=tool_call.name,
        )
        final_request = GenerationRequest(
            messages=[
                *initial_messages,
                assistant_tool_message,
                tool_result_message,
            ]
        )

        try:
            final_response = self._generate(final_request)
        except LLMProviderError as exc:
            return self._provider_failure(
                exc,
                tool_name=tool_call.name,
                tool_result=tool_result,
            )
        except Exception:
            logger.exception("unexpected advisor final-generation failure")
            return self._internal_failure(
                tool_name=tool_call.name,
                tool_result=tool_result,
            )

        if final_response.tool_calls:
            return AdvisorResponse(
                text="I could not safely process an additional tool call in this request.",
                tool_name=tool_call.name,
                tool_result=tool_result,
                requires_human_review=_requires_human_review(tool_result),
            )

        return AdvisorResponse(
            text=final_response.content or "",
            tool_name=tool_call.name,
            tool_result=tool_result,
            requires_human_review=_requires_human_review(tool_result),
        )

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        response = self._llm_service.generate(request)
        if not isinstance(response, GenerationResponse):
            raise InvalidProviderResponseError
        return response

    @staticmethod
    def _provider_failure(
        error: LLMProviderError,
        *,
        tool_name: str | None = None,
        tool_result: dict[str, Any] | None = None,
    ) -> AdvisorResponse:
        if isinstance(error, ProviderTimeoutError):
            text = "The advisor service timed out before it could complete the request."
        elif isinstance(error, ProviderUnavailableError):
            text = "The advisor service is currently unavailable. Please try again later."
        elif isinstance(error, InvalidProviderResponseError):
            text = "The advisor service returned an invalid response."
        elif isinstance(error, ProviderExecutionError):
            text = "The advisor service could not complete the request."
        else:
            text = "The advisor service could not safely complete the request."
        return AdvisorResponse(
            text=text,
            tool_name=tool_name,
            tool_result=tool_result,
            requires_human_review=_requires_human_review(tool_result),
        )

    @staticmethod
    def _tool_failure(tool_name: str, error: ToolError) -> AdvisorResponse:
        code, message = _safe_tool_error(error)
        return AdvisorResponse(
            text=message,
            tool_name=tool_name,
            tool_result={"error": {"code": code, "message": message}},
        )

    @staticmethod
    def _internal_failure(
        *,
        tool_name: str | None = None,
        tool_result: dict[str, Any] | None = None,
    ) -> AdvisorResponse:
        return AdvisorResponse(
            text="The advisor could not safely complete the request.",
            tool_name=tool_name,
            tool_result=tool_result,
            requires_human_review=_requires_human_review(tool_result),
        )


def _requires_human_review(tool_result: dict[str, Any] | None) -> bool:
    return tool_result is not None and tool_result.get("requires_human_review") is True


def _safe_tool_error(error: ToolError) -> tuple[str, str]:
    if isinstance(error, UnknownToolError):
        return (
            "UNKNOWN_TOOL",
            "The requested tool is an unknown tool or unavailable.",
        )
    if isinstance(error, ToolArgumentValidationError):
        return (
            "INVALID_TOOL_ARGUMENTS",
            "The academic request contained invalid tool arguments.",
        )
    if isinstance(error, ToolDataUnavailableError):
        return (
            "TOOL_DATA_UNAVAILABLE",
            "Required academic data is unavailable.",
        )
    if isinstance(error, ToolContextRequiredError):
        return (
            "TRUSTED_CONTEXT_UNAVAILABLE",
            "Trusted student context is unavailable.",
        )
    if isinstance(error, ToolExecutionError):
        return (
            "TOOL_EXECUTION_FAILED",
            "The academic tool could not complete safely.",
        )
    return (
        "TOOL_FAILED",
        "The academic tool could not complete safely.",
    )


__all__ = ["AdvisorOrchestrator"]
