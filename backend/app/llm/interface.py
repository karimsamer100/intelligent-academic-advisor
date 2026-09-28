"""The replaceable provider seam for local LLM runtimes."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from app.llm.contracts import GenerationRequest, GenerationResponse

StructuredT = TypeVar("StructuredT", bound=BaseModel)


@runtime_checkable
class LLMProvider(Protocol):
    """Provider contract consumed by the application service."""

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate one provider-neutral response for ``request``."""

        ...

    def generate_structured(
        self,
        request: GenerationRequest,
        response_model: type[StructuredT],
    ) -> StructuredT:
        """Generate and validate a structured response for ``response_model``."""

        ...


__all__ = ["LLMProvider"]
