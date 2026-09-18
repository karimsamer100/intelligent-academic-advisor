from __future__ import annotations
from abc import ABC, abstractmethod
from app.rag.models.domain import DocumentMetadata, RetrievedEvidence, RetrievalFilters, SourceState, StoredChunk


class ChunkRepository(ABC):
    @abstractmethod
    def get_source_state(self, source_id: str) -> SourceState | None:
        raise NotImplementedError

    @abstractmethod
    def replace_source(self, source: DocumentMetadata, chunks: list[StoredChunk]) -> int:
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        filters: RetrievalFilters,
        top_k: int,
        min_score: float | None = None,
    ) -> list[RetrievedEvidence]:
        raise NotImplementedError
