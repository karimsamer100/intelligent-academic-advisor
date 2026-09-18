from __future__ import annotations
from app.rag.retrieval.service import DocumentSearchService
from app.schemas.rag import RAGSearchRequest, RAGSearchResponse


class RAGService:
    """Backend-facing boundary. It returns evidence only; no LLM answer generation occurs here."""

    def __init__(self, search_service: DocumentSearchService) -> None:
        self.search_service = search_service

    def search(self, request: RAGSearchRequest) -> RAGSearchResponse:
        results = self.search_service.search_documents(
            query=request.query,
            regulation=request.regulation,
            program=request.program,
            document_types=request.document_types,
            language=request.language,
            official_status=request.official_status,
            top_k=request.top_k,
        )
        return RAGSearchResponse(results=results)
