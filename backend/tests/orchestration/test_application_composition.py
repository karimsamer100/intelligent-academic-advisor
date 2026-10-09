from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.requests import Request

import app.api.deps as api_deps
from app.core.config import Settings
from app.llm.contracts import GenerationRequest, GenerationResponse, ToolCall
from app.orchestration.composition import (
    AdvisorApplication,
    build_advisor_application,
    build_advisor_static_dependencies,
)
from app.orchestration.contracts import AdvisorRequest
from app.rag import provider as rag_provider
from app.rag.embeddings.hash_test_provider import HashTestEmbeddingProvider
from app.rag.models.domain import ChunkDraft, DocumentMetadata, StoredChunk
from app.rag.repositories.pgvector_repository import PgVectorChunkRepository
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService
from app.tools.errors import ToolCompositionError


class QueueProvider:
    """Deterministic provider fake for composed offline advisor turns."""

    def __init__(self, responses: list[GenerationResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("the fake provider ran out of responses")
        return self.responses.pop(0)

    def generate_structured(
        self,
        request: GenerationRequest,
        response_model: type[BaseModel],
    ) -> BaseModel:
        raise AssertionError("structured generation is not part of this test")


class EmptyRetriever:
    def search(self, request):
        del request
        return []


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _settings() -> Settings:
    root = _repo_root()
    return Settings(
        _env_file=None,
        academic_data_foundation_path=root / "data" / "academic_foundation",
        student_data_path=root / "data" / "students" / "students.json",
    )


def _static_dependencies():
    return build_advisor_static_dependencies(_settings())


def _application(
    provider: QueueProvider,
    *,
    static_dependencies=None,
    rag_service: RAGService | None = None,
) -> AdvisorApplication:
    static = static_dependencies or _static_dependencies()
    return build_advisor_application(
        llm_service=LLMService(provider),
        planning_service=static.planning_service,
        rag_service=rag_service or RAGService(EmptyRetriever()),
        student_repository=static.student_repository,
        academic_data=static.academic_data,
    )


def _call(name: str, arguments: dict[str, Any], call_id: str = "call-1") -> ToolCall:
    return ToolCall(call_id=call_id, name=name, arguments=arguments)


def test_fastapi_composition_reuses_app_owned_static_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    app = FastAPI()
    request = Request({"type": "http", "app": app})
    monkeypatch.setattr(api_deps, "get_settings", lambda: settings)

    first = api_deps.get_advisor_static_dependencies(request)
    second = api_deps.get_advisor_static_dependencies(request)

    assert first is second
    assert first.planning_service is second.planning_service
    assert first.academic_data is second.academic_data
    assert first.student_repository is second.student_repository
    assert first.planning_service._engine is second.planning_service._engine
    assert app.state.advisor_static_dependencies is first


def test_composed_orchestrator_executes_real_eligibility_and_delivers_compact_result() -> None:
    provider = QueueProvider(
        [
            GenerationResponse(
                tool_calls=[
                    _call("check_course_eligibility", {"course_code": "CSE221"})
                ]
            ),
            GenerationResponse(content="The modeled result is available."),
        ]
    )
    static = _static_dependencies()
    application = _application(provider, static_dependencies=static)

    response = application.orchestrator.respond(
        AdvisorRequest(
            user_message="Can I take CSE221?",
            student_id="DEV-STUDENT-001",
        )
    )

    assert response.tool_name == "check_course_eligibility"
    assert response.tool_result is not None
    assert response.tool_result["course"] == {
        "code": "CSE221",
        "name": "Logic Design and Computer Organization",
    }
    assert response.tool_result["decision"] == "ELIGIBLE"
    assert response.tool_result["authoritative"] is False
    assert response.requires_human_review is False
    assert len(provider.requests) == 2
    assert provider.requests[1].tools
    assert provider.requests[1].messages[-1].content == json.dumps(
        response.tool_result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    eligibility_tool = application.tool_registry.get("check_course_eligibility")
    assert eligibility_tool._student_repository is static.student_repository
    assert eligibility_tool._planning_service is static.planning_service


def test_composed_orchestrator_executes_real_degree_audit_and_preserves_review_state() -> None:
    provider = QueueProvider(
        [
            GenerationResponse(tool_calls=[_call("degree_audit", {})]),
            GenerationResponse(content="The modeled audit requires human review."),
        ]
    )
    application = _application(provider)

    response = application.orchestrator.respond(
        AdvisorRequest(
            user_message="Audit my degree progress.",
            student_id="DEV-STUDENT-001",
        )
    )

    assert response.tool_name == "degree_audit"
    assert response.tool_result is not None
    assert response.tool_result["requirement_set_status"] == "INCOMPLETE"
    assert response.tool_result["authoritative"] is False
    assert response.tool_result["requires_human_review"] is True
    assert response.requires_human_review is True
    assert len(provider.requests) == 2


def test_composed_tool_boundary_rejects_llm_scope_override() -> None:
    provider = QueueProvider(
        [
            GenerationResponse(
                tool_calls=[
                    _call(
                        "check_course_eligibility",
                        {
                            "course_code": "CSE221",
                            "student_id": "FORGED-STUDENT",
                            "regulation": 1,
                            "program": "FORGED",
                        },
                    )
                ]
            )
        ]
    )
    application = _application(provider)

    response = application.orchestrator.respond(
        AdvisorRequest(
            user_message="Use this other academic identity.",
            student_id="DEV-STUDENT-001",
        )
    )

    assert response.tool_result == {
        "error": {
            "code": "INVALID_TOOL_ARGUMENTS",
            "message": "The academic request contained invalid tool arguments.",
        }
    }
    assert len(provider.requests) == 1


def _rag_source() -> DocumentMetadata:
    return DocumentMetadata(
        source_id="CHECKPOINT2-COMPOSE-SOURCE",
        file_name="checkpoint2.pdf",
        document_title="Checkpoint 2 composition source",
        document_types=["REGULATION"],
        regulations=[2023],
        programs=["CAIE"],
        languages=["en"],
        effective_year=2023,
        version="test",
        official_status="official",
        file_hash=hashlib.sha256(b"checkpoint2-composition").hexdigest(),
        relative_path="tests/checkpoint2.pdf",
        page_count=1,
    )


def _rag_chunk(provider: HashTestEmbeddingProvider) -> StoredChunk:
    content = "The 2023 regulation defines the maximum credit load."
    draft = ChunkDraft(
        chunk_id="CHECKPOINT2-COMPOSE-CHUNK",
        source_id="CHECKPOINT2-COMPOSE-SOURCE",
        text=content,
        page_start=1,
        page_end=1,
        section="Credit load",
        document_type="REGULATION",
        regulation=2023,
        program="CAIE",
        language="en",
        topic="credit_load",
        chunk_index=0,
        text_hash=hashlib.sha256(content.encode()).hexdigest(),
        applicable_document_types=["REGULATION"],
        applicable_regulations=[2023],
        applicable_programs=["CAIE"],
    )
    return StoredChunk(
        **draft.model_dump(),
        embedding=provider.embed_documents([content])[0],
        embedding_model=provider.model_name,
        pipeline_version="checkpoint2-test",
        official_status="official",
    )


@pytest.mark.integration
def test_composed_orchestrator_executes_real_request_scoped_rag(
    db_engine,
) -> None:
    embedder = HashTestEmbeddingProvider(dimension=1024)
    connection = db_engine.connect()
    session = Session(bind=connection, expire_on_commit=False)
    repository = PgVectorChunkRepository(session)
    repository.replace_source(_rag_source(), [_rag_chunk(embedder)])
    session.flush()

    try:
        rag_service = RAGService(
            rag_provider.get_retriever(session, embedder=embedder)
        )
        provider = QueueProvider(
            [
                GenerationResponse(
                    tool_calls=[
                        _call(
                            "search_official_documents",
                            {
                                "query": "maximum credit load",
                                "document_types": ["REGULATION"],
                            },
                        )
                    ]
                ),
                GenerationResponse(content="The evidence is available on page 1."),
            ]
        )
        application = _application(provider, rag_service=rag_service)

        response = application.orchestrator.respond(
            AdvisorRequest(
                user_message="What is the maximum credit load?",
                student_id="DEV-STUDENT-001",
            )
        )

        assert response.tool_result is not None
        assert response.tool_result["results"][0]["source_id"] == (
            "CHECKPOINT2-COMPOSE-SOURCE"
        )
        assert response.tool_result["results"][0]["page_start"] == 1
        assert "CHECKPOINT2-COMPOSE-SOURCE" in provider.requests[1].messages[-1].content
        assert application.rag_service is rag_service
        assert application.tool_registry.get(
            "search_official_documents"
        )._rag_service is rag_service
        assert rag_service._retriever.search_service.repository.session is session
        assert session.is_active
    finally:
        session.rollback()
        session.close()
        connection.close()


def test_composition_fails_closed_when_academic_data_is_missing(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        academic_data_foundation_path=tmp_path / "missing-academic-data",
        student_data_path=_settings().student_data_path,
    )

    with pytest.raises(ToolCompositionError):
        build_advisor_static_dependencies(settings)


def test_composed_tool_fails_safely_for_unknown_trusted_student() -> None:
    provider = QueueProvider(
        [
            GenerationResponse(
                tool_calls=[
                    _call("check_course_eligibility", {"course_code": "CSE221"})
                ]
            )
        ]
    )
    application = _application(provider)

    response = application.orchestrator.respond(
        AdvisorRequest(
            user_message="Can I take CSE221?",
            student_id="UNKNOWN-STUDENT",
        )
    )

    assert response.tool_result == {
        "error": {
            "code": "TOOL_DATA_UNAVAILABLE",
            "message": "Required academic data is unavailable.",
        }
    }
    assert len(provider.requests) == 1
