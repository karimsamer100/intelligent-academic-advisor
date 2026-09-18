from app.rag.embeddings.hash_test_provider import HashTestEmbeddingProvider
from app.rag.models.domain import DocumentMetadata, StoredChunk
from app.rag.repositories.memory_repository import MemoryChunkRepository
from app.rag.retrieval.service import DocumentSearchService


def make_source(source_id, reg):
    return DocumentMetadata(
        source_id=source_id,
        file_name=f"{source_id}.pdf",
        document_title=source_id,
        document_types=["REGULATION"],
        regulations=[reg],
        programs=["CAIE"],
        languages=["en"],
        official_status="OFFICIAL",
        file_hash=("a" if reg == 2018 else "b") * 64,
    )


def make_chunk(embedder, source_id, reg, text):
    return StoredChunk(
        chunk_id=f"{source_id}:C1",
        source_id=source_id,
        text=text,
        page_start=1,
        page_end=1,
        section="Rules",
        document_type="REGULATION",
        regulation=reg,
        program="CAIE",
        language="en",
        topic="credit_load",
        chunk_index=1,
        applicable_document_types=["REGULATION"],
        applicable_regulations=[reg],
        applicable_programs=["CAIE"],
        text_hash=("c" if reg == 2018 else "d") * 64,
        metadata={},
        embedding=embedder.embed_query(text),
        embedding_model=embedder.model_name,
        pipeline_version="test",
        official_status="OFFICIAL",
    )


def test_trusted_regulation_filter_prevents_cross_contamination():
    embedder = HashTestEmbeddingProvider(64)
    repo = MemoryChunkRepository()
    repo.replace_source(make_source("SRC18", 2018), [make_chunk(embedder, "SRC18", 2018, "maximum credit load registration")])
    repo.replace_source(make_source("SRC23", 2023), [make_chunk(embedder, "SRC23", 2023, "maximum credit load registration")])
    service = DocumentSearchService(embedder, repo)

    results = service.search_documents("maximum credit load", regulation=2023, program="CAIE", top_k=5)
    assert results
    assert all(r.source_id == "SRC23" for r in results)
    assert all(r.regulation == 2023 for r in results)
