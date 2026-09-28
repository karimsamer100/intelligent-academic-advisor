"""Small per-application registry for provider-neutral academic tools."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel

from app.llm.contracts import ToolDefinition
from app.tools.context import ToolExecutionContext
from app.tools.errors import ToolDuplicateNameError, UnknownToolError
from app.tools.interface import AcademicTool


class ToolRegistry:
    """Resolve and expose one explicitly composed set of academic tools."""

    def __init__(self, tools: Iterable[AcademicTool[Any]] = ()) -> None:
        self._tools: dict[str, AcademicTool[Any]] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: AcademicTool[Any]) -> None:
        """Register one tool under its stable provider-neutral name."""

        if not isinstance(tool, AcademicTool):
            raise TypeError("tool must be an AcademicTool")
        name = tool.definition.name
        if name in self._tools:
            raise ToolDuplicateNameError(name)
        self._tools[name] = tool

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        """Return definitions in deterministic name order."""

        return tuple(self._tools[name].definition for name in sorted(self._tools))

    def get(self, name: str) -> AcademicTool[Any]:
        """Resolve a tool by exact, case-sensitive name."""

        if not isinstance(name, str) or name not in self._tools:
            raise UnknownToolError(name if isinstance(name, str) else "<invalid>")
        return self._tools[name]

    def execute(
        self,
        name: str,
        arguments: Mapping[str, Any] | BaseModel,
        trusted_context: ToolExecutionContext,
    ) -> dict[str, Any]:
        """Resolve and execute a tool; argument validation remains tool-owned."""

        return self.get(name).execute(arguments, trusted_context)


__all__ = ["ToolRegistry"]
