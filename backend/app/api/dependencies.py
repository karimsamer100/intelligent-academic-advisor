from __future__ import annotations

from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.services.rag_service import RAGService


@lru_cache(maxsize=1)
def get_embedding_provider():
    # Lazy imports keep health/schema tests independent from heavy production RAG deps.
    from app.rag.embeddings.sentence_transformer import SentenceTransformerEmbeddingProvider

    settings = get_settings()
    return SentenceTransformerEmbeddingProvider(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
        expected_dimension=settings.embedding_dimension,
        cache_dir=settings.embedding_cache_dir,
        batch_size=settings.embedding_batch_size,
    )


def get_rag_service(db: Session = Depends(get_db)) -> RAGService:
    from app.rag.repositories.pgvector_repository import PgVectorChunkRepository
    from app.rag.retrieval.service import DocumentSearchService

    settings = get_settings()
    search_service = DocumentSearchService(
        embedder=get_embedding_provider(),
        repository=PgVectorChunkRepository(db),
        default_top_k=settings.rag_top_k,
        max_top_k=settings.rag_max_top_k,
        min_score=settings.rag_min_score,
    )
    return RAGService(search_service)
