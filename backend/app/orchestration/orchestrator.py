"""Bounded provider-neutral orchestration for grounded advisor responses."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.llm.contracts import (
    GenerationRequest,
    GenerationResponse,
    LLMMessage,
    MessageRole,
    ToolCall,
)
from app.llm.errors import (
    InvalidProviderResponseError,
    LLMProviderError,
    ProviderExecutionError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.orchestration.contracts import (
    AdvisorRequest,
    AdvisorResponse,
    AdvisorToolExecution,
)
from app.orchestration.prompts import ADVISOR_SYSTEM_PROMPT
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

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AdvisorOrchestrationLimits:
    """Explicit per-turn safety limits for tool execution.

    These defaults bound the current orchestration behavior; they are not a
    product-level claim that the limits cannot change in a later decision.
    """

    max_tool_rounds: int = 3
    max_tool_executions: int = 5

    def __post_init__(self) -> None:
        if self.max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be positive")
        if self.max_tool_executions < 1:
            raise ValueError("max_tool_executions must be positive")


class AdvisorOrchestrator:
    """Coordinate bounded LLM tool rounds with trusted backend context."""

    def __init__(
        self,
        llm_service: LLMService,
        tool_registry: ToolRegistry,
        *,
        system_prompt: str = ADVISOR_SYSTEM_PROMPT,
        limits: AdvisorOrchestrationLimits | None = None,
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
        self._limits = limits or AdvisorOrchestrationLimits()

    def respond(self, request: AdvisorRequest) -> AdvisorResponse:
        """Return a direct answer or a bounded sequence of grounded rounds."""

        if not isinstance(request, AdvisorRequest):
            raise TypeError("request must be an AdvisorRequest")

        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=self._system_prompt),
            LLMMessage(role=MessageRole.USER, content=request.user_message),
        ]
        executions: list[AdvisorToolExecution] = []
        seen_requests: set[tuple[str, str]] = set()
        tool_rounds = 0
        total_executions = 0
        tools_enabled = True

        while True:
            generation_request = GenerationRequest(
                messages=list(messages),
                tools=list(self._tool_registry.definitions) if tools_enabled else [],
            )
            try:
                generation_response = self._generate(generation_request)
            except LLMProviderError as exc:
                return self._provider_failure(
                    exc,
                    executions=executions,
                    transcript=messages,
                )
            except Exception:
                logger.exception("unexpected advisor provider failure")
                return self._internal_failure(
                    executions=executions,
                    transcript=messages,
                )

            if not generation_response.tool_calls:
                messages.append(
                    LLMMessage(
                        role=MessageRole.ASSISTANT,
                        content=generation_response.content or "",
                    )
                )
                return self._response(
                    generation_response.content or "The advisor returned no answer.",
                    executions=executions,
                    transcript=messages,
                )

            round_index = tool_rounds + 1
            tool_calls = _normalize_tool_calls(
                generation_response.tool_calls,
                round_index=round_index,
            )
            messages.append(
                LLMMessage(
                    role=MessageRole.ASSISTANT,
                    content=generation_response.content,
                    tool_calls=tool_calls,
                )
            )

            if not tools_enabled:
                reason = _budget_reason(
                    tool_rounds=tool_rounds,
                    total_executions=total_executions,
                    limits=self._limits,
                )
                return self._reject_batch(
                    tool_calls,
                    round_index=round_index,
                    code=reason[0],
                    message=reason[1],
                    executions=executions,
                    transcript=messages,
                )

            validation = self._validate_batch(
                tool_calls,
                tool_rounds=tool_rounds,
                total_executions=total_executions,
                seen_requests=seen_requests,
            )
            if validation.rejection is not None:
                return self._reject_batch(
                    tool_calls,
                    round_index=round_index,
                    code=validation.rejection[0],
                    message=validation.rejection[1],
                    per_call_errors=validation.errors,
                    executions=executions,
                    transcript=messages,
                )

            tool_rounds += 1
            total_executions += len(validation.calls)
            batch_execution_start = len(executions)
            for call, validated_arguments, request_key in validation.calls:
                seen_requests.add(request_key)
                arguments = _model_arguments(validated_arguments)
                trusted_context = ToolExecutionContext(student_id=request.student_id)
                status = "executed"
                try:
                    tool_result = self._tool_registry.execute(
                        call.name,
                        validated_arguments,
                        trusted_context,
                    )
                    tool_message_content = _serialize_tool_result(tool_result)
                except ToolError as exc:
                    status = "failed"
                    code, message = _safe_tool_error(exc)
                    tool_result = {"error": {"code": code, "message": message}}
                    tool_message_content = _serialize_tool_result(tool_result)
                except Exception:
                    logger.exception(
                        "unexpected advisor tool failure",
                        extra={"tool_name": call.name},
                    )
                    status = "failed"
                    tool_result = {
                        "error": {
                            "code": "TOOL_EXECUTION_FAILED",
                            "message": "The academic tool could not complete safely.",
                        }
                    }
                    tool_message_content = _serialize_tool_result(tool_result)

                executions.append(
                    AdvisorToolExecution(
                        call_id=call.call_id or "missing-call-id",
                        tool_name=call.name,
                        arguments=arguments,
                        status=status,
                        round_index=round_index,
                        result=tool_result,
                    )
                )
                messages.append(
                    LLMMessage(
                        role=MessageRole.TOOL,
                        content=tool_message_content,
                        tool_call_id=call.call_id,
                        tool_name=call.name,
                    )
                )

            batch_executions = executions[batch_execution_start:]
            if batch_executions and all(
                execution.status == "failed" for execution in batch_executions
            ):
                first_result = batch_executions[0].result or {}
                error = first_result.get("error") if isinstance(first_result, dict) else None
                failure_text = (
                    error.get("message")
                    if isinstance(error, dict) and isinstance(error.get("message"), str)
                    else "The academic tools could not complete safely."
                )
                return self._response(
                    failure_text,
                    executions=executions,
                    transcript=messages,
                )

            tools_enabled = not (
                tool_rounds >= self._limits.max_tool_rounds
                or total_executions >= self._limits.max_tool_executions
            )

    def _validate_batch(
        self,
        tool_calls: list[ToolCall],
        *,
        tool_rounds: int,
        total_executions: int,
        seen_requests: set[tuple[str, str]],
    ) -> "_BatchValidation":
        if tool_rounds >= self._limits.max_tool_rounds:
            return _BatchValidation(
                rejection=(
                    "TOOL_ROUND_LIMIT_EXCEEDED",
                    "The advisor reached the tool round limit for this request.",
                )
            )
        if total_executions + len(tool_calls) > self._limits.max_tool_executions:
            return _BatchValidation(
                rejection=(
                    "TOOL_EXECUTION_LIMIT_EXCEEDED",
                    "The advisor reached the tool execution limit for this request.",
                )
            )

        validated_calls: list[tuple[ToolCall, BaseModel, tuple[str, str]]] = []
        errors: dict[str, tuple[str, str]] = {}
        batch_keys: set[tuple[str, str]] = set()
        for call in tool_calls:
            try:
                tool = self._tool_registry.get(call.name)
            except UnknownToolError:
                errors[call.call_id or "missing-call-id"] = _safe_tool_error(
                    UnknownToolError(call.name)
                )
                continue

            try:
                validated_arguments = tool.validate_arguments(call.arguments)
                request_key = (
                    call.name,
                    _canonical_json(_model_arguments(validated_arguments)),
                )
            except ToolArgumentValidationError as exc:
                errors[call.call_id or "missing-call-id"] = _safe_tool_error(exc)
                continue
            except (TypeError, ValueError):
                errors[call.call_id or "missing-call-id"] = (
                    "INVALID_TOOL_ARGUMENTS",
                    "The academic request contained invalid tool arguments.",
                )
                continue

            if request_key in seen_requests or request_key in batch_keys:
                errors[call.call_id or "missing-call-id"] = (
                    "REPEATED_TOOL_CALL",
                    "The advisor requested a repeated tool call.",
                )
                continue
            batch_keys.add(request_key)
            validated_calls.append((call, validated_arguments, request_key))

        if errors:
            call_ids = [call.call_id or "missing-call-id" for call in tool_calls]
            if not all(call_id in errors for call_id in call_ids):
                return _BatchValidation(
                    rejection=(
                        "INVALID_TOOL_BATCH",
                        "The advisor could not safely validate the complete tool-call batch.",
                    ),
                    errors=errors,
                )
            first_error = errors[next(iter(errors))]
            return _BatchValidation(rejection=first_error, errors=errors)

        return _BatchValidation(calls=validated_calls)

    def _reject_batch(
        self,
        tool_calls: list[ToolCall],
        *,
        round_index: int,
        code: str,
        message: str,
        executions: list[AdvisorToolExecution],
        transcript: list[LLMMessage],
        per_call_errors: dict[str, tuple[str, str]] | None = None,
    ) -> AdvisorResponse:
        for call in tool_calls:
            call_id = call.call_id or "missing-call-id"
            call_error = (per_call_errors or {}).get(call_id, (code, message))
            result = {"error": {"code": call_error[0], "message": call_error[1]}}
            executions.append(
                AdvisorToolExecution(
                    call_id=call_id,
                    tool_name=call.name,
                    arguments=call.arguments,
                    status="rejected",
                    round_index=round_index,
                    result=result,
                )
            )
            transcript.append(
                LLMMessage(
                    role=MessageRole.TOOL,
                    content=_serialize_tool_result(result),
                    tool_call_id=call_id,
                    tool_name=call.name,
                )
            )
        return self._response(message, executions=executions, transcript=transcript)

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        response = self._llm_service.generate(request)
        if not isinstance(response, GenerationResponse):
            raise InvalidProviderResponseError
        return response

    @staticmethod
    def _response(
        text: str,
        *,
        executions: list[AdvisorToolExecution],
        transcript: list[LLMMessage],
    ) -> AdvisorResponse:
        legacy_name, legacy_result = _legacy_tool_fields(executions)
        return AdvisorResponse(
            text=text,
            tool_name=legacy_name,
            tool_result=legacy_result,
            requires_human_review=any(
                _requires_human_review(execution.result)
                for execution in executions
                if execution.status != "rejected"
            ),
            tool_executions=list(executions),
            transcript=list(transcript),
        )

    @classmethod
    def _provider_failure(
        cls,
        error: LLMProviderError,
        *,
        executions: list[AdvisorToolExecution],
        transcript: list[LLMMessage],
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
        return cls._response(text, executions=executions, transcript=transcript)

    @classmethod
    def _internal_failure(
        cls,
        *,
        executions: list[AdvisorToolExecution],
        transcript: list[LLMMessage],
    ) -> AdvisorResponse:
        return cls._response(
            "The advisor could not safely complete the request.",
            executions=executions,
            transcript=transcript,
        )


@dataclass(frozen=True, slots=True)
class _BatchValidation:
    calls: list[tuple[ToolCall, BaseModel, tuple[str, str]]] = field(
        default_factory=list
    )
    rejection: tuple[str, str] | None = None
    errors: dict[str, tuple[str, str]] | None = None


def _normalize_tool_calls(tool_calls: list[ToolCall], *, round_index: int) -> list[ToolCall]:
    normalized: list[ToolCall] = []
    used_ids: set[str] = set()
    for index, call in enumerate(tool_calls, start=1):
        call_id = call.call_id or f"call-{round_index}-{index}"
        if call_id in used_ids:
            suffix = 2
            candidate = f"{call_id}-{suffix}"
            while candidate in used_ids:
                suffix += 1
                candidate = f"{call_id}-{suffix}"
            call_id = candidate
        used_ids.add(call_id)
        normalized.append(
            ToolCall(call_id=call_id, name=call.name, arguments=call.arguments)
        )
    return normalized


def _model_arguments(arguments: BaseModel) -> dict[str, Any]:
    return arguments.model_dump(mode="json", exclude_none=False)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _serialize_tool_result(tool_result: dict[str, Any]) -> str:
    return _canonical_json(tool_result)


def _budget_reason(
    *,
    tool_rounds: int,
    total_executions: int,
    limits: AdvisorOrchestrationLimits,
) -> tuple[str, str]:
    if tool_rounds >= limits.max_tool_rounds:
        return (
            "TOOL_ROUND_LIMIT_EXCEEDED",
            "The advisor reached the tool round limit for this request.",
        )
    if total_executions >= limits.max_tool_executions:
        return (
            "TOOL_EXECUTION_LIMIT_EXCEEDED",
            "The advisor reached the tool execution limit for this request.",
        )
    return (
        "TOOL_EXECUTION_DISABLED",
        "The advisor could not safely process another tool call.",
    )


def _legacy_tool_fields(
    executions: list[AdvisorToolExecution],
) -> tuple[str | None, dict[str, Any] | None]:
    actual = [
        execution
        for execution in executions
        if execution.status in {"executed", "failed"}
    ]
    if len(actual) == 1:
        return actual[0].tool_name, actual[0].result
    if not actual and len(executions) == 1:
        return executions[0].tool_name, executions[0].result
    return None, None


def _requires_human_review(tool_result: dict[str, Any] | None) -> bool:
    if tool_result is None:
        return False
    if tool_result.get("requires_human_review") is True:
        return True
    for key in ("status", "decision", "outcome"):
        value = tool_result.get(key)
        if isinstance(value, str) and value.upper() in {
            "INDETERMINATE",
            "HUMAN_REVIEW_REQUIRED",
        }:
            return True
    return False


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


__all__ = ["AdvisorOrchestrationLimits", "AdvisorOrchestrator"]
