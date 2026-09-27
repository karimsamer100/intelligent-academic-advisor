"""Provider-neutral contracts for the Local LLM boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MessageRole(StrEnum):
    """Roles supported by the provider-neutral message contract."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class _LLMModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ToolCall(_LLMModel):
    """A structured tool request returned by an LLM provider."""

    call_id: str | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, Any]


class LLMMessage(_LLMModel):
    """A provider-neutral message exchanged with an LLM."""

    role: MessageRole
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _validate_role_semantics(self) -> "LLMMessage":
        has_content = bool(self.content)

        if self.role in {MessageRole.SYSTEM, MessageRole.USER} and not has_content:
            raise ValueError(f"{self.role.value} messages require content")

        if self.role is MessageRole.ASSISTANT:
            if not has_content and not self.tool_calls:
                raise ValueError("assistant messages require content or tool_calls")
        elif self.role is MessageRole.TOOL:
            if not has_content:
                raise ValueError("tool messages require content")
            if self.tool_call_id is None:
                raise ValueError("tool messages require tool_call_id")

        if self.role is not MessageRole.ASSISTANT and self.tool_calls:
            raise ValueError("only assistant messages may contain tool_calls")

        if self.role is not MessageRole.TOOL and self.tool_call_id is not None:
            raise ValueError("only tool messages may contain tool_call_id")

        return self


class ToolDefinition(_LLMModel):
    """A provider-neutral description of a callable tool."""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict[str, Any]


class GenerationRequest(_LLMModel):
    """Input supplied to an LLM provider for one generation request."""

    messages: list[LLMMessage] = Field(min_length=1)
    tools: list[ToolDefinition] = Field(default_factory=list)
    temperature: float | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _reject_duplicate_tool_names(self) -> "GenerationRequest":
        names = [tool.name for tool in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("tools must not contain duplicate names")
        return self


class GenerationResponse(_LLMModel):
    """Provider output containing assistant text, tool calls, or both."""

    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _require_content_or_tool_calls(self) -> "GenerationResponse":
        if not self.content and not self.tool_calls:
            raise ValueError("generation responses require content or tool_calls")
        return self


__all__ = [
    "GenerationRequest",
    "GenerationResponse",
    "LLMMessage",
    "MessageRole",
    "ToolCall",
    "ToolDefinition",
]
