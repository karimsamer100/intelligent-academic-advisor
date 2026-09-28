"""Small generic application-tool contract for future orchestration."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.contracts import ToolDefinition
from app.tools.context import ToolExecutionContext
from app.tools.errors import (
    ToolArgumentValidationError,
    ToolExecutionError,
)

ArgumentsT = TypeVar("ArgumentsT", bound=BaseModel)


class AcademicTool(ABC, Generic[ArgumentsT]):
    """Base contract shared by provider-neutral academic tools."""

    name: ClassVar[str]
    description: ClassVar[str]
    arguments_model: ClassVar[type[ArgumentsT]]

    @property
    def definition(self) -> ToolDefinition:
        """Return the provider-neutral definition sent to an LLM provider."""

        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.arguments_model.model_json_schema(),
        )

    def validate_arguments(self, arguments: Mapping[str, Any] | ArgumentsT) -> ArgumentsT:
        """Validate one raw provider tool-call argument mapping."""

        if isinstance(arguments, self.arguments_model):
            return arguments
        try:
            return self.arguments_model.model_validate(arguments)
        except (TypeError, ValidationError):
            raise ToolArgumentValidationError(self.name) from None

    def execute(
        self,
        arguments: Mapping[str, Any] | ArgumentsT,
        trusted_context: ToolExecutionContext,
    ) -> dict[str, Any]:
        """Validate arguments, execute the tool, and enforce JSON output."""

        if not isinstance(trusted_context, ToolExecutionContext):
            raise TypeError("trusted_context must be a ToolExecutionContext")

        validated_arguments = self.validate_arguments(arguments)
        result = self._execute(validated_arguments, trusted_context)
        if not isinstance(result, Mapping):
            raise ToolExecutionError(self.name)

        payload = dict(result)
        try:
            json.dumps(payload, allow_nan=False)
        except (TypeError, ValueError):
            raise ToolExecutionError(self.name) from None
        return payload

    @abstractmethod
    def _execute(
        self,
        arguments: ArgumentsT,
        trusted_context: ToolExecutionContext,
    ) -> Mapping[str, Any]:
        """Execute already-validated arguments against trusted dependencies."""


__all__ = ["AcademicTool"]
