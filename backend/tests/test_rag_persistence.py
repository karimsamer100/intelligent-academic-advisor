from __future__ import annotations

import hashlib
import re

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import models as _db_models  # noqa: F401
from app.db.base import Base
from app.rag.embeddings.hash_test_provider import HashTestEmbeddingProvider
from app.rag.models.domain import (
    ChunkDraft,
    DocumentMetadata,
    StoredChunk,
)

pytestmark = pytest.mark.integration

EXPECTED_SOURCE_COLUMNS = {
    "source_id",
    "file_name",
    "document_title",
    "document_types",
    "regulations",
    "programs",
    "languages",
    "effective_year",
    "version",
    "official_status",
    "file_hash",
    "relative_path",
    "authority_level",
    "verification_state",
    "page_count",
    "source_metadata",
    "embedding_model",
    "pipeline_version",
    "expected_chunk_count",
    "ingested_at",
}

EXPECTED_CHUNK_COLUMNS = {
    "chunk_id",
    "source_id",
    "text",
    "text_hash",
    "embedding",
    "page_start",
    "page_end",
    "section",
    "document_type",
    "regulation",
    "program",
    "language",
    "topic",
    "chunk_index",
    "applicable_document_types",
    "applicable_regulations",
    "applicable_programs",
    "official_status",
    "embedding_model",
    "pipeline_version",
    "chunk_metadata",
    "ingested_at",
}


def _columns(db_engine, table_name: str) -> set[str]:
    with db_engine.connect() as connection:
        return set(
            connection.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = :table_name
                    """
                ),
                {"table_name": table_name},
            ).scalars()
        )


def _source() -> DocumentMetadata:
    return DocumentMetadata(
        source_id="CHECKPOINT3-RAG-PERSISTENCE",
        file_name="checkpoint3.pdf",
        document_title="Checkpoint 3 RAG persistence contract",
        document_types=["REGULATION", "GUIDE"],
        regulations=[18, 23],
        programs=["CAIE", "CESS"],
        languages=["en"],
        effective_year=2026,
        version="test",
        official_status="TEST_ONLY",
        file_hash=hashlib.sha256(b"checkpoint3").hexdigest(),
        relative_path="tests/checkpoint3.pdf",
        authority_level="test",
        verification_state="verified",
        page_count=3,
        source_metadata={"checkpoint": 3},
    )


def _stored_chunks(
    provider: HashTestEmbeddingProvider,
    source: DocumentMetadata,
) -> list[StoredChunk]:
    specifications = [
        (
            "CHECKPOINT3-REG23-CAIE",
            "credit load regulation 23 CAIE",
            "REGULATION",
            23,
            "CAIE",
        ),
        (
            "CHECKPOINT3-REG18-CESS",
            "credit load regulation 18 CESS",
            "REGULATION",
            18,
            "CESS",
        ),
        (
            "CHECKPOINT3-GUIDE-CAIE",
            "credit load registration guide CAIE",
            "GUIDE",
            23,
            "CAIE",
        ),
    ]
    chunks: list[StoredChunk] = []
    for index, (chunk_id, content, document_type, regulation, program) in enumerate(
        specifications
    ):
        draft = ChunkDraft(
            chunk_id=chunk_id,
            source_id=source.source_id,
            text=content,
            page_start=index + 1,
            page_end=index + 1,
            section="Credit load",
            document_type=document_type,
            regulation=regulation,
            program=program,
            language="en",
            topic="credit_load",
            chunk_index=index,
            text_hash=hashlib.sha256(content.encode()).hexdigest(),
            applicable_document_types=[document_type],
            applicable_regulations=[regulation],
            applicable_programs=[program],
            metadata={"checkpoint": 3, "index": index},
        )
        chunks.append(
            StoredChunk(
                **draft.model_dump(),
                embedding=provider.embed_documents([content])[0],
                embedding_model=provider.model_name,
                pipeline_version="checkpoint3-test",
                official_status=source.official_status,
            )
        )
    return chunks


def test_alembic_reaches_integrated_rag_head(db_engine) -> None:
    with db_engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert revision == "0002"


def test_rag_tables_have_expected_columns_and_vector_contract(db_engine) -> None:
    assert EXPECTED_SOURCE_COLUMNS <= _columns(db_engine, "rag_sources")
    assert EXPECTED_CHUNK_COLUMNS <= _columns(db_engine, "rag_chunks")

    with db_engine.connect() as connection:
        vector_type = connection.execute(
            text(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute AS a
                WHERE a.attrelid = 'public.rag_chunks'::regclass
                  AND a.attname = 'embedding'
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                """
            )
        ).scalar_one()
    assert vector_type == "vector(1024)"


def test_rag_orm_registration_matches_fixed_schema_dimension() -> None:
    assert "rag_sources" in Base.metadata.tables
    assert "rag_chunks" in Base.metadata.tables

    from app.rag.models.orm import RagChunk

    configured_dimension = Settings(_env_file=None).embedding_dimension
    assert configured_dimension == 1024
    assert RagChunk.__table__.c.embedding.type.dim == configured_dimension


def test_rag_indexes_have_required_definitions(db_engine) -> None:
    with db_engine.connect() as connection:
        indexes = dict(
            connection.execute(
                text(
                    """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename IN ('rag_sources', 'rag_chunks')
                    """
                )
            ).all()
        )

    required = {
        "ix_rag_sources_official_status",
        "ix_rag_chunks_source_id",
        "ix_rag_chunks_document_type",
        "ix_rag_chunks_regulation",
        "ix_rag_chunks_program",
        "ix_rag_chunks_language",
        "ix_rag_chunks_topic",
        "ix_rag_chunks_official_status",
        "ix_rag_chunks_applicable_document_types",
        "ix_rag_chunks_applicable_regulations",
        "ix_rag_chunks_applicable_programs",
        "ix_rag_chunks_embedding_hnsw",
    }
    assert required <= indexes.keys()

    hnsw_definition = re.sub(
        r"\s+", " ", indexes["ix_rag_chunks_embedding_hnsw"].lower()
    )
    assert "using hnsw" in hnsw_definition
    assert "vector_cosine_ops" in hnsw_definition
    assert re.search(r"\bm\s*=\s*'?16'?", hnsw_definition)
    assert re.search(r"\bef_construction\s*=\s*'?64'?", hnsw_definition)


def test_pgvector_repository_retrieval_filters_and_replacement(db_engine) -> None:
    from app.rag.models.orm import RagChunk
    from app.rag.repositories.pgvector_repository import PgVectorChunkRepository
    from app.rag.retrieval.service import DocumentSearchService

    provider = HashTestEmbeddingProvider(dimension=1024)
    source = _source()
    chunks = _stored_chunks(provider, source)
    session = Session(bind=db_engine, expire_on_commit=False)
    repository = PgVectorChunkRepository(session)
    service = DocumentSearchService(
        embedder=provider,
        repository=repository,
        default_top_k=10,
        max_top_k=20,
    )

    try:
        assert repository.replace_source(source, chunks) == 3
        assert repository.replace_source(source, chunks) == 3
        assert session.scalar(
            select(func.count())
            .select_from(RagChunk)
            .where(RagChunk.source_id == source.source_id)
        ) == 3

        all_results = service.search_documents("credit load", top_k=10)
        assert {result.chunk_id for result in all_results} == {
            chunk.chunk_id for chunk in chunks
        }

        regulation_results = service.search_documents(
            "credit load",
            regulation=23,
            top_k=10,
        )
        assert {result.chunk_id for result in regulation_results} == {
            "CHECKPOINT3-REG23-CAIE",
            "CHECKPOINT3-GUIDE-CAIE",
        }

        program_results = service.search_documents(
            "credit load",
            program="CESS",
            top_k=10,
        )
        assert {result.chunk_id for result in program_results} == {
            "CHECKPOINT3-REG18-CESS"
        }

        document_type_results = service.search_documents(
            "credit load",
            document_types=["REGULATION"],
            top_k=10,
        )
        assert {result.chunk_id for result in document_type_results} == {
            "CHECKPOINT3-REG23-CAIE",
            "CHECKPOINT3-REG18-CESS",
        }

        replacement = [chunks[0].model_copy(update={"chunk_id": "CHECKPOINT3-REPLACED"})]
        assert repository.replace_source(source, replacement) == 1
        state = repository.get_source_state(source.source_id)
        assert state is not None
        assert state.chunk_count == 1
        assert session.scalar(
            select(func.count())
            .select_from(RagChunk)
            .where(RagChunk.source_id == source.source_id)
        ) == 1
    finally:
        session.rollback()
        session.close()
