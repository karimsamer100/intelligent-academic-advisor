"""Backend adapter for the concrete RAG document search service."""

from __future__ import annotations

from collections.abc import Sequence

from app.rag.models.domain import RetrievedEvidence
from app.rag.retrieval.service import DocumentSearchService
from app.schemas.rag import RAGRequest, RAGResult


def normalize_regulation(regulation: int | None) -> int | None:
    """Translate short RAG regulation identifiers to persisted calendar years."""
    return {18: 2018, 23: 2023}.get(regulation, regulation)


class PgVectorRetriever:
    """Translate the backend RAG contract to ``DocumentSearchService``."""

    def __init__(self, search_service: DocumentSearchService) -> None:
        self._search_service = search_service

    @property
    def search_service(self) -> DocumentSearchService:
        return self._search_service

    def search(self, request: RAGRequest) -> Sequence[RAGResult]:
        evidence = self._search_service.search_documents(
            query=request.query,
            regulation=normalize_regulation(request.regulation),
            program=request.program,
            document_types=request.document_types,
            language=request.language,
            official_status=request.official_status,
            top_k=request.top_k,
        )
        return [self._to_result(item) for item in evidence]

    @staticmethod
    def _to_result(evidence: RetrievedEvidence) -> RAGResult:
        return RAGResult(
            chunk_id=evidence.chunk_id,
            text=evidence.text,
            score=evidence.score,
            source_id=evidence.source_id,
            file_name=evidence.file_name,
            page_start=evidence.page_start,
            page_end=evidence.page_end,
            section=evidence.section,
            document_type=evidence.document_type,
            regulation=evidence.regulation,
            program=evidence.program,
            language=evidence.language,
        )
