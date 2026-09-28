"""Safe provider-domain errors for the LLM boundary."""


class LLMProviderError(Exception):
    """Base error that a concrete LLM provider may expose to the application."""

    message = "LLM provider error"

    def __init__(self) -> None:
        super().__init__(self.message)


class ProviderUnavailableError(LLMProviderError):
    """The provider cannot be reached or is not available."""

    message = "LLM provider is unavailable"


class ProviderTimeoutError(LLMProviderError):
    """The provider did not complete within its configured timeout."""

    message = "LLM provider request timed out"


class ProviderExecutionError(LLMProviderError):
    """The provider failed while executing a generation request."""

    message = "LLM provider execution failed"


class InvalidProviderResponseError(LLMProviderError):
    """The provider returned a response that violates the LLM contract."""

    message = "LLM provider returned an invalid response"


class StructuredOutputValidationError(LLMProviderError):
    """The provider returned JSON that failed the requested Pydantic schema."""

    message = "LLM structured output failed schema validation"


__all__ = [
    "InvalidProviderResponseError",
    "LLMProviderError",
    "ProviderExecutionError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "StructuredOutputValidationError",
]
