from __future__ import annotations

import logging
from app.rag.embeddings.base import EmbeddingProvider
from app.rag.metadata.taxonomy import canonical_document_type
from app.rag.models.domain import RetrievedEvidence, RetrievalFilters
from app.rag.repositories.base import ChunkRepository

logger = logging.getLogger(__name__)


class DocumentSearchService:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        repository: ChunkRepository,
        default_top_k: int = 5,
        max_top_k: int = 20,
        min_score: float | None = None,
    ) -> None:
        self.embedder = embedder
        self.repository = repository
        self.default_top_k = default_top_k
        self.max_top_k = max_top_k
        self.min_score = min_score

    def search_documents(
        self,
        query: str,
        regulation: int | None = None,
        program: str | None = None,
        document_types: list[str] | None = None,
        language: str | None = None,
        official_status: str | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedEvidence]:
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        k = self.default_top_k if top_k is None else top_k
        if k <= 0 or k > self.max_top_k:
            raise ValueError(f"top_k must be between 1 and {self.max_top_k}")
        canonical_types = [canonical_document_type(x) or x for x in document_types] if document_types else None
        filters = RetrievalFilters(
            regulation=regulation,
            program=program,
            document_types=canonical_types,
            language=language,
            official_status=official_status,
        )
        logger.info(
            "RAG retrieval query",
            extra={"filters": filters.model_dump(exclude_none=True)},
        )
        query_vector = self.embedder.embed_query(query)
        results = self.repository.search(query_vector, filters, k, self.min_score)
        logger.info("RAG retrieval complete", extra={"result_count": len(results)})
        return results
