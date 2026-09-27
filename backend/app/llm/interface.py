"""The replaceable provider seam for local LLM runtimes."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.llm.contracts import GenerationRequest, GenerationResponse


@runtime_checkable
class LLMProvider(Protocol):
    """Provider contract consumed by the application service."""

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate one provider-neutral response for ``request``."""

        ...


__all__ = ["LLMProvider"]
