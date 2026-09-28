from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.llm.contracts import ToolDefinition
from app.tools.context import ToolExecutionContext
from app.tools.errors import ToolArgumentValidationError
from app.tools.interface import AcademicTool


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    value: str = Field(min_length=1)


class EchoTool(AcademicTool[EchoArguments]):
    name = "echo_tool"
    description = "Echo one validated value."
    arguments_model = EchoArguments

    def _execute(
        self,
        arguments: EchoArguments,
        trusted_context: ToolExecutionContext,
    ) -> dict[str, Any]:
        return {"value": arguments.value, "student_id": trusted_context.student_id}


def test_tool_definition_is_provider_neutral_and_matches_argument_model() -> None:
    definition = EchoTool().definition

    assert isinstance(definition, ToolDefinition)
    assert definition.name == "echo_tool"
    assert set(definition.input_schema["properties"]) == {"value"}
    assert definition.input_schema["required"] == ["value"]


def test_tool_validates_arguments_before_execution() -> None:
    result = EchoTool().execute(
        {"value": "ok"},
        ToolExecutionContext(student_id="student-001"),
    )

    assert result == {"value": "ok", "student_id": "student-001"}


def test_tool_rejects_unknown_arguments() -> None:
    with pytest.raises(ToolArgumentValidationError):
        EchoTool().execute(
            {"value": "ok", "student_id": "forged"},
            ToolExecutionContext(student_id="student-001"),
        )

