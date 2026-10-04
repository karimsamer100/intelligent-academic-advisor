from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.requests import Request

import app.api.deps as api_deps
import app.main as app_main
from app.core.config import Settings
from app.llm.providers.ollama import OllamaProvider
from app.services.llm_service import LLMService


class RecordingHttpClient:
    def __init__(self, *, timeout: Any) -> None:
        self.timeout = timeout
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_base_url="http://configured-ollama.test",
        llm_model="configured-model",
        llm_timeout_seconds=17.25,
    )


def test_lifespan_owns_shared_client_and_provider_uses_configured_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    created_clients: list[RecordingHttpClient] = []

    def create_client(*, timeout: Any) -> RecordingHttpClient:
        client = RecordingHttpClient(timeout=timeout)
        created_clients.append(client)
        return client

    monkeypatch.setattr(app_main, "httpx", SimpleNamespace(Client=create_client))
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    monkeypatch.setattr(api_deps, "get_settings", lambda: settings)
    monkeypatch.setattr(app_main, "dispose_engine", lambda: None)

    app = FastAPI()

    async def exercise_lifespan() -> None:
        async with app_main.lifespan(app):
            assert len(created_clients) == 1
            shared_client = created_clients[0]
            assert app.state.llm_http_client is shared_client
            assert shared_client.timeout == pytest.approx(settings.llm_timeout_seconds)

            provider = api_deps.get_llm_provider(Request({"type": "http", "app": app}))

            assert isinstance(provider, OllamaProvider)
            assert provider._client is shared_client
            assert provider._settings is settings
            assert provider._settings.llm_base_url == "http://configured-ollama.test"
            assert provider._settings.llm_model == "configured-model"
            assert shared_client.close_calls == 0

        assert created_clients[0].close_calls == 1

    asyncio.run(exercise_lifespan())


def test_get_llm_service_wraps_provider_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    shared_client = RecordingHttpClient(timeout=settings.llm_timeout_seconds)
    app = FastAPI()
    app.state.llm_http_client = shared_client
    monkeypatch.setattr(api_deps, "get_settings", lambda: settings)

    provider = api_deps.get_llm_provider(Request({"type": "http", "app": app}))
    service = api_deps.get_llm_service(provider)

    assert isinstance(provider, OllamaProvider)
    assert isinstance(service, LLMService)
    assert service._provider is provider
