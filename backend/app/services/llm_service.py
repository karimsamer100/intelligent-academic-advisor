"""Application boundary over the provider-neutral LLM interface."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.llm.contracts import GenerationRequest, GenerationResponse
from app.llm.interface import LLMProvider

StructuredT = TypeVar("StructuredT", bound=BaseModel)


class LLMService:
    """Thin application adapter that delegates generation to an injected provider."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        return self._provider.generate(request)

    def generate_structured(
        self,
        request: GenerationRequest,
        response_model: type[StructuredT],
    ) -> StructuredT:
        return self._provider.generate_structured(request, response_model)


__all__ = ["LLMService"]
