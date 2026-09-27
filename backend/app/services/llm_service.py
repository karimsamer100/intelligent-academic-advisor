"""Application boundary over the provider-neutral LLM interface."""

from __future__ import annotations

from app.llm.contracts import GenerationRequest, GenerationResponse
from app.llm.interface import LLMProvider


class LLMService:
    """Thin application adapter that delegates generation to an injected provider."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        return self._provider.generate(request)


__all__ = ["LLMService"]
