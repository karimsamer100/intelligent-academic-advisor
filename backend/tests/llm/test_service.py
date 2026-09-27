from __future__ import annotations

import pytest

from app.llm.contracts import GenerationRequest, GenerationResponse, LLMMessage, MessageRole
from app.llm.errors import ProviderExecutionError
from app.services.llm_service import LLMService


class RecordingProvider:
    def __init__(self, response: GenerationResponse | None = None, error: Exception | None = None) -> None:
        self.response = response or GenerationResponse(content="provider response")
        self.error = error
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


def _request() -> GenerationRequest:
    return GenerationRequest(
        messages=[LLMMessage(role=MessageRole.USER, content="What is the rule?")]
    )


def test_llm_service_delegates_the_exact_request_and_response_unchanged() -> None:
    response = GenerationResponse(content="The provider answer.")
    provider = RecordingProvider(response=response)
    service = LLMService(provider)
    request = _request()

    actual = service.generate(request)

    assert provider.requests == [request]
    assert provider.requests[0] is request
    assert actual is response


def test_llm_service_supports_replacing_the_provider() -> None:
    first_response = GenerationResponse(content="first")
    second_response = GenerationResponse(content="second")
    request = _request()

    first = LLMService(RecordingProvider(response=first_response))
    second = LLMService(RecordingProvider(response=second_response))

    assert first.generate(request) is first_response
    assert second.generate(request) is second_response


def test_llm_service_propagates_provider_error_unchanged() -> None:
    error = ProviderExecutionError()
    service = LLMService(RecordingProvider(error=error))

    with pytest.raises(ProviderExecutionError) as raised:
        service.generate(_request())

    assert raised.value is error
