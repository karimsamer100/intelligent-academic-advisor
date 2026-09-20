import logging

from app.core.exceptions import RAGNotConfiguredError
from app.rag.interface import Retriever
from app.schemas.rag import RAGRequest, RAGResponse

logger = logging.getLogger(__name__)


class RAGService:
    """The backend's only entry point to retrieval.

    Routes talk to this class; this class talks to whatever ``Retriever`` was
    injected. It knows nothing about embeddings or vector search.
    """

    def __init__(self, retriever: Retriever | None = None) -> None:
        self._retriever = retriever

    def search(self, request: RAGRequest) -> RAGResponse:
        if self._retriever is None:
            raise RAGNotConfiguredError()

        # Enforce the caller's top_k here so every retriever behaves the same.
        results = list(self._retriever.search(request))[: request.top_k]
        logger.info(
            "rag search completed",
            extra={"result_count": len(results), "top_k": request.top_k, "query_length": len(request.query)},
        )
        return RAGResponse(results=results)
