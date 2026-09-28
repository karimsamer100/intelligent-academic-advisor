from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.tools.context import ToolExecutionContext
from app.tools.errors import (
    ToolArgumentValidationError,
    ToolDuplicateNameError,
    UnknownToolError,
)
from app.tools.interface import AcademicTool
from app.tools.registry import ToolRegistry


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


class ZuluTool(EchoTool):
    name = "zulu_tool"


class DuplicateEchoTool(EchoTool):
    name = "echo_tool"


def test_registry_definitions_are_deterministically_sorted() -> None:
    registry = ToolRegistry([ZuluTool(), EchoTool()])

    assert [definition.name for definition in registry.definitions] == [
        "echo_tool",
        "zulu_tool",
    ]


def test_registry_resolves_exact_tool_names() -> None:
    tool = EchoTool()
    registry = ToolRegistry([tool])

    assert registry.get("echo_tool") is tool

    with pytest.raises(UnknownToolError):
        registry.get("Echo_Tool")


def test_registry_rejects_duplicate_tool_names() -> None:
    with pytest.raises(ToolDuplicateNameError):
        ToolRegistry([EchoTool(), DuplicateEchoTool()])


def test_registry_unknown_tool_execution_fails_safely() -> None:
    with pytest.raises(UnknownToolError):
        ToolRegistry().execute("missing_tool", {}, ToolExecutionContext())


def test_registry_executes_tools_and_preserves_argument_validation() -> None:
    registry = ToolRegistry([EchoTool()])

    result = registry.execute(
        "echo_tool",
        {"value": "ok"},
        ToolExecutionContext(student_id="student-001"),
    )

    assert result == {"value": "ok", "student_id": "student-001"}

    with pytest.raises(ToolArgumentValidationError):
        registry.execute(
            "echo_tool",
            {"value": "ok", "student_id": "forged"},
            ToolExecutionContext(student_id="student-001"),
        )
