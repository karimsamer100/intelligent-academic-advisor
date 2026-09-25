from __future__ import annotations

import hashlib

import pytest
from sqlalchemy.orm import Session

from app.api.deps import get_health_service, get_retriever
from app.core.config import get_settings
from app.db.session import get_db
from app.rag.embeddings.hash_test_provider import HashTestEmbeddingProvider
from app.rag.models.domain import ChunkDraft, DocumentMetadata, StoredChunk
from app.rag.repositories.pgvector_repository import PgVectorChunkRepository
from app.rag.retrieval.service import DocumentSearchService
from app.rag.retriever import PgVectorRetriever
from app.services.health_service import HealthService


def _source() -> DocumentMetadata:
    return DocumentMetadata(
        source_id="CHECKPOINT4-API-SOURCE",
        file_name="checkpoint4.pdf",
        document_title="Checkpoint 4 API boundary",
        document_types=["REGULATION"],
        regulations=[2023],
        programs=["CAIE"],
        languages=["en"],
        effective_year=2023,
        version="test",
        official_status="official",
        file_hash=hashlib.sha256(b"checkpoint4-api").hexdigest(),
        relative_path="tests/checkpoint4.pdf",
        page_count=1,
    )


def _stored_chunk(provider: HashTestEmbeddingProvider) -> StoredChunk:
    content = "The maximum credit load is defined by the 2023 regulation."
    draft = ChunkDraft(
        chunk_id="CHECKPOINT4-API-CHUNK",
        source_id="CHECKPOINT4-API-SOURCE",
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
        pipeline_version="checkpoint4-test",
        official_status="official",
    )


def test_embedding_provider_factory_is_lazy_and_cached(monkeypatch) -> None:
    import app.rag.provider as provider

    constructed: list[tuple[tuple, dict]] = []

    class FakeSentenceTransformerProvider:
        def __init__(self, *args, **kwargs) -> None:
            constructed.append((args, kwargs))

    monkeypatch.setattr(provider, "SentenceTransformerEmbeddingProvider", FakeSentenceTransformerProvider)
    provider.get_embedding_provider.cache_clear()
    try:
        assert constructed == []
        first = provider.get_embedding_provider()
        second = provider.get_embedding_provider()

        assert first is second
        assert len(constructed) == 1
        assert constructed[0][0][0] == get_settings().embedding_model
        assert constructed[0][1]["device"] == get_settings().embedding_device
        assert constructed[0][1]["expected_dimension"] == get_settings().embedding_dimension
        assert constructed[0][1]["batch_size"] == get_settings().embedding_batch_size
    finally:
        provider.get_embedding_provider.cache_clear()


def test_database_retriever_is_request_scoped_and_not_cached(monkeypatch) -> None:
    import app.rag.provider as provider

    embedder = HashTestEmbeddingProvider(dimension=1024)
    monkeypatch.setattr(provider, "get_embedding_provider", lambda: embedder)
    first_session = Session()
    second_session = Session()
    try:
        first = provider.get_retriever(first_session)
        second = provider.get_retriever(second_session)

        assert first is not second
        assert first.search_service.embedder is not second.search_service.embedder
        assert first.search_service.embedder.model_name == get_settings().embedding_model
        assert first.search_service.embedder.dimension == get_settings().embedding_dimension
        assert first.search_service.embedder.embed_query("credit load") == embedder.embed_query("credit load")
        assert second.search_service.embedder.embed_query("credit load") == embedder.embed_query("credit load")
        assert first.search_service.repository.session is first_session
        assert second.search_service.repository.session is second_session
    finally:
        first_session.close()
        second_session.close()


def test_health_and_readiness_do_not_construct_embedding_model(app, client, monkeypatch) -> None:
    import app.rag.provider as provider

    def fail_if_constructed(*args, **kwargs):
        raise AssertionError("embedding model must not be constructed by health checks")

    class ReadyRepository:
        def ping(self) -> None:
            return None

        def get_pgvector_version(self) -> str:
            return "0.8.0"

    monkeypatch.setattr(provider, "SentenceTransformerEmbeddingProvider", fail_if_constructed)
    app.dependency_overrides[get_health_service] = lambda: HealthService(ReadyRepository())
    try:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/ready").status_code == 200
        assert client.post("/api/v1/rag/search", json={"query": "", "top_k": 0}).status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_search_route_uses_real_adapter_with_deterministic_provider_and_db(
    app, client, db_engine, monkeypatch
) -> None:
    import app.rag.provider as provider

    embedder = HashTestEmbeddingProvider(dimension=1024)
    connection = db_engine.connect()
    session = Session(bind=connection, expire_on_commit=False)
    repository = PgVectorChunkRepository(session)
    repository.replace_source(_source(), [_stored_chunk(embedder)])
    session.flush()

    def override_db():
        yield session

    monkeypatch.setattr(provider, "get_embedding_provider", lambda: embedder)
    app.dependency_overrides[get_db] = override_db
    try:
        response = client.post(
            "/api/v1/rag/search",
            json={
                "query": "maximum credit load",
                "regulation": 23,
                "program": "CAIE",
                "document_types": ["REGULATION"],
                "top_k": 1,
            },
        )
    finally:
        app.dependency_overrides.clear()
        session.rollback()
        session.close()
        connection.close()

    assert response.status_code == 200, response.text
    assert response.json()["results"] == [
        {
            "chunk_id": "CHECKPOINT4-API-CHUNK",
            "text": "The maximum credit load is defined by the 2023 regulation.",
            "score": pytest.approx(0.5),
            "source_id": "CHECKPOINT4-API-SOURCE",
            "file_name": "checkpoint4.pdf",
            "page_start": 1,
            "page_end": 1,
            "section": "Credit load",
            "document_type": "REGULATION",
            "regulation": 2023,
            "program": "CAIE",
            "language": "en",
        }
    ]
