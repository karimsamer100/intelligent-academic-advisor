"""Small per-application registry for provider-neutral academic tools."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel

from app.llm.contracts import ToolDefinition
from app.tools.context import ToolExecutionContext
from app.tools.errors import (
    ToolDuplicateNameError,
    ToolError,
    ToolExecutionError,
    UnknownToolError,
)
from app.tools.interface import AcademicTool

logger = logging.getLogger(__name__)


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
        """Execute a tool while preserving expected and sanitizing unexpected errors."""

        tool = self.get(name)
        try:
            return tool.execute(arguments, trusted_context)
        except ToolError:
            raise
        except Exception:
            logger.exception("tool execution failed", extra={"tool_name": tool.name})
            raise ToolExecutionError(tool.name) from None


__all__ = ["ToolRegistry"]
