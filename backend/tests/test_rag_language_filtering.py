from __future__ import annotations

import hashlib

from app.rag.embeddings.hash_test_provider import HashTestEmbeddingProvider
from app.rag.models.domain import (
    ChunkDraft,
    DocumentMetadata,
    RetrievalFilters,
    StoredChunk,
)
from app.rag.repositories.memory_repository import MemoryChunkRepository


def _source() -> DocumentMetadata:
    return DocumentMetadata(
        source_id="LANGUAGE-FILTER-SOURCE",
        file_name="language-filter.pdf",
        document_title="Language filter regression",
        document_types=["REGULATION"],
        regulations=[2023],
        programs=["CAIE"],
        languages=["en", "ar"],
        official_status="official",
        file_hash=hashlib.sha256(b"language-filter").hexdigest(),
    )


def _chunk(
    provider: HashTestEmbeddingProvider,
    *,
    chunk_id: str,
    language: str,
    text: str,
) -> StoredChunk:
    draft = ChunkDraft(
        chunk_id=chunk_id,
        source_id="LANGUAGE-FILTER-SOURCE",
        text=text,
        page_start=1,
        page_end=1,
        section="Language filter",
        document_type="REGULATION",
        regulation=2023,
        program="CAIE",
        language=language,
        topic="language_filter",
        chunk_index=0 if language == "en" else 1,
        text_hash=hashlib.sha256(text.encode()).hexdigest(),
        applicable_document_types=["REGULATION"],
        applicable_regulations=[2023],
        applicable_programs=["CAIE"],
    )
    return StoredChunk(
        **draft.model_dump(),
        embedding=provider.embed_documents([text])[0],
        embedding_model=provider.model_name,
        pipeline_version="language-filter-test",
        official_status="official",
    )


def test_underlying_memory_rag_language_filter_remains_available() -> None:
    provider = HashTestEmbeddingProvider(dimension=16)
    repository = MemoryChunkRepository()
    repository.replace_source(
        _source(),
        [
            _chunk(
                provider,
                chunk_id="LANGUAGE-FILTER-EN",
                language="en",
                text="English official regulation evidence.",
            ),
            _chunk(
                provider,
                chunk_id="LANGUAGE-FILTER-AR",
                language="ar",
                text="Arabic official regulation evidence.",
            ),
        ],
    )

    english_results = repository.search(
        provider.embed_query("official regulation evidence"),
        RetrievalFilters(language="en"),
        top_k=5,
    )
    arabic_results = repository.search(
        provider.embed_query("official regulation evidence"),
        RetrievalFilters(language="ar"),
        top_k=5,
    )

    assert [result.chunk_id for result in english_results] == ["LANGUAGE-FILTER-EN"]
    assert [result.chunk_id for result in arabic_results] == ["LANGUAGE-FILTER-AR"]
