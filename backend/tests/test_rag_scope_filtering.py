from __future__ import annotations

import hashlib

from app.rag.embeddings.hash_test_provider import HashTestEmbeddingProvider
from app.rag.models.domain import (
    ChunkDraft,
    DocumentMetadata,
    RetrievedEvidence,
    RetrievalFilters,
    StoredChunk,
)
from app.rag.repositories.memory_repository import MemoryChunkRepository


def _source() -> DocumentMetadata:
    return DocumentMetadata(
        source_id="SCOPE-FILTER-SOURCE",
        file_name="Bylaw 2023.pdf",
        document_title="General Bylaw 2023",
        document_types=["REGULATION"],
        regulations=[2018, 2023],
        programs=["CAIE", "CESS"],
        languages=["en"],
        official_status="official",
        file_hash=hashlib.sha256(b"scope-filter").hexdigest(),
    )


def _stored_chunk(
    provider: HashTestEmbeddingProvider,
    *,
    chunk_id: str,
    applicable_regulations: list[int],
    applicable_programs: list[str],
    regulation: int | None = None,
    program: str | None = None,
) -> StoredChunk:
    content = f"University bylaw scope test for {chunk_id}."
    draft = ChunkDraft(
        chunk_id=chunk_id,
        source_id="SCOPE-FILTER-SOURCE",
        text=content,
        page_start=1,
        page_end=1,
        section="General rules",
        document_type="REGULATION",
        regulation=regulation,
        program=program,
        applicable_document_types=["REGULATION"],
        applicable_regulations=applicable_regulations,
        applicable_programs=applicable_programs,
        language="en",
        topic="general",
        chunk_index=0,
        text_hash=hashlib.sha256(content.encode()).hexdigest(),
    )
    return StoredChunk(
        **draft.model_dump(),
        embedding=provider.embed_documents([content])[0],
        embedding_model=provider.model_name,
        pipeline_version="scope-filter-test",
        official_status="official",
    )


def _search(
    *,
    applicable_regulations: list[int],
    applicable_programs: list[str],
    regulation: int | None = None,
    program: str | None = None,
) -> list[RetrievedEvidence]:
    provider = HashTestEmbeddingProvider(dimension=16)
    repository = MemoryChunkRepository()
    repository.replace_source(
        _source(),
        [
            _stored_chunk(
                provider,
                chunk_id="SCOPE-FILTER-CHUNK",
                applicable_regulations=applicable_regulations,
                applicable_programs=applicable_programs,
                regulation=regulation,
                program=program,
            )
        ],
    )
    return repository.search(
        provider.embed_query("university bylaw"),
        RetrievalFilters(regulation=regulation, program=program),
        top_k=5,
    )


def test_general_document_survives_trusted_program_filter() -> None:
    results = _search(
        applicable_regulations=[],
        applicable_programs=[],
        program="CAIE",
    )

    assert [result.chunk_id for result in results] == ["SCOPE-FILTER-CHUNK"]


def test_wrong_specific_program_is_excluded() -> None:
    results = _search(
        applicable_regulations=[2023],
        applicable_programs=["CESS"],
        regulation=2023,
        program="CAIE",
    )

    assert results == []


def test_general_document_survives_trusted_regulation_filter() -> None:
    results = _search(
        applicable_regulations=[],
        applicable_programs=[],
        regulation=2023,
    )

    assert [result.chunk_id for result in results] == ["SCOPE-FILTER-CHUNK"]


def test_wrong_specific_regulation_is_excluded() -> None:
    results = _search(
        applicable_regulations=[2018],
        applicable_programs=[],
        regulation=2023,
    )

    assert results == []


def test_combined_trusted_context_keeps_regulation_specific_general_chunk() -> None:
    results = _search(
        applicable_regulations=[2023],
        applicable_programs=[],
        regulation=2023,
        program="CAIE",
    )

    assert [result.chunk_id for result in results] == ["SCOPE-FILTER-CHUNK"]
