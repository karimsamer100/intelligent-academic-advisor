"""Small application contracts for one grounded advisor turn."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _AdvisorModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class AdvisorRequest(_AdvisorModel):
    """Trusted input for one stateless advisor request."""

    user_message: str = Field(min_length=1)
    student_id: str = Field(min_length=1)


class AdvisorResponse(_AdvisorModel):
    """The intentionally small result of one advisor turn."""

    text: str = Field(min_length=1)
    tool_name: str | None = Field(default=None, min_length=1)
    tool_result: dict[str, Any] | None = None
    requires_human_review: bool = False


__all__ = ["AdvisorRequest", "AdvisorResponse"]
