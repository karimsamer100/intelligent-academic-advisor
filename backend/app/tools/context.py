"""Server-owned context passed separately from LLM-controlled tool arguments."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.planning.domain.student import StudentState
from app.planning.repositories.student_repository import (
    StudentRepository,
    StudentRepositoryError,
)
from app.tools.errors import ToolContextRequiredError, ToolDataUnavailableError


class ToolExecutionContext(BaseModel):
    """Minimal trusted context owned by the future session/orchestration layer."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    student_id: str | None = Field(default=None, min_length=1)


def resolve_student_state(
    context: ToolExecutionContext,
    repository: StudentRepository,
    tool_name: str,
) -> StudentState:
    """Resolve the canonical student state without accepting LLM overrides."""

    if context.student_id is None:
        raise ToolContextRequiredError(tool_name)

    try:
        student = repository.get_student_state(context.student_id)
    except StudentRepositoryError:
        raise ToolDataUnavailableError(tool_name) from None

    if student is None:
        raise ToolDataUnavailableError(tool_name)
    return student


__all__ = ["ToolExecutionContext", "resolve_student_state"]
