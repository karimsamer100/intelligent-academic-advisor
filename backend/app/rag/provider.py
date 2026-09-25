"""Factories for the process-wide embedder and request-scoped retriever."""

from collections.abc import Callable
from functools import lru_cache

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.rag.embeddings.base import EmbeddingProvider
from app.rag.embeddings.sentence_transformer import SentenceTransformerEmbeddingProvider
from app.rag.interface import Retriever
from app.rag.repositories.pgvector_repository import PgVectorChunkRepository
from app.rag.retrieval.service import DocumentSearchService
from app.rag.retriever import PgVectorRetriever


class LazyEmbeddingProvider(EmbeddingProvider):
    """Resolve the expensive provider only when a query needs an embedding."""

    def __init__(
        self,
        factory: Callable[[], EmbeddingProvider],
        model_name: str,
        dimension: int,
    ) -> None:
        self._factory = factory
        self._model_name = model_name
        self._dimension = dimension
        self._provider: EmbeddingProvider | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _loaded_provider(self) -> EmbeddingProvider:
        if self._provider is None:
            self._provider = self._factory()
        return self._provider

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._loaded_provider().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._loaded_provider().embed_query(text)


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    """Create the expensive runtime embedder only when first retrieval occurs."""
    settings = get_settings()
    return SentenceTransformerEmbeddingProvider(
        settings.embedding_model,
        device=settings.embedding_device,
        expected_dimension=settings.embedding_dimension,
        cache_dir=settings.embedding_cache_dir,
        batch_size=settings.embedding_batch_size,
    )


def get_retriever(
    db: Session,
    embedder: EmbeddingProvider | None = None,
) -> Retriever:
    """Build a retriever around the caller's request-scoped database session."""
    settings = get_settings()
    selected_embedder = (
        embedder
        if embedder is not None
        else LazyEmbeddingProvider(
            get_embedding_provider,
            model_name=settings.embedding_model,
            dimension=settings.embedding_dimension,
        )
    )
    search_service = DocumentSearchService(
        embedder=selected_embedder,
        repository=PgVectorChunkRepository(db),
        default_top_k=settings.rag_top_k,
        max_top_k=settings.rag_max_top_k,
        min_score=settings.rag_min_score,
    )
    return PgVectorRetriever(search_service)
