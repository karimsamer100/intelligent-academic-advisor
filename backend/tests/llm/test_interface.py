from __future__ import annotations

import pytest

from app.llm.contracts import GenerationRequest, GenerationResponse
from app.llm.errors import (
    InvalidProviderResponseError,
    LLMProviderError,
    ProviderExecutionError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.llm.interface import LLMProvider


class FakeProvider:
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(content=request.messages[0].content or "")


def test_provider_protocol_accepts_a_replaceable_fake() -> None:
    assert isinstance(FakeProvider(), LLMProvider)
    assert hasattr(LLMProvider, "generate")
    assert not hasattr(LLMProvider, "generate_structured")


@pytest.mark.parametrize(
    "error_type",
    [
        ProviderUnavailableError,
        ProviderTimeoutError,
        ProviderExecutionError,
        InvalidProviderResponseError,
    ],
)
def test_provider_errors_share_the_llm_provider_error_boundary(error_type: type[LLMProviderError]) -> None:
    error = error_type()

    assert isinstance(error, LLMProviderError)
    assert str(error)
