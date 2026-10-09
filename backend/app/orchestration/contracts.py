"""Provider-neutral contracts for one grounded advisor turn."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.llm.contracts import LLMMessage


class _AdvisorModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class AdvisorRequest(_AdvisorModel):
    """Trusted input for one stateless advisor request."""

    user_message: str = Field(min_length=1)
    student_id: str = Field(min_length=1)


class AdvisorToolExecution(_AdvisorModel):
    """One ordered tool-call outcome from an advisor turn."""

    call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]
    status: Literal["executed", "failed", "rejected"]
    round_index: int = Field(ge=1)
    result: dict[str, Any] | None = None


class AdvisorResponse(_AdvisorModel):
    """The stateless result of one bounded advisor turn.

    ``tool_name`` and ``tool_result`` remain for single-tool consumers.  They
    are populated only when the outcome can be represented without hiding
    multiple execution records; callers handling multi-tool turns should use
    ``tool_executions`` and ``transcript``.
    """

    text: str = Field(min_length=1)
    tool_name: str | None = Field(default=None, min_length=1)
    tool_result: dict[str, Any] | None = None
    requires_human_review: bool = False
    tool_executions: list[AdvisorToolExecution] = Field(default_factory=list)
    transcript: list[LLMMessage] = Field(default_factory=list)


__all__ = ["AdvisorRequest", "AdvisorResponse", "AdvisorToolExecution"]
