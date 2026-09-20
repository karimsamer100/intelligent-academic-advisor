"""The seam between the backend and the RAG implementation.

The RAG module (extraction, chunking, embeddings, vector search) only has to
provide an object with this ``search`` method. The backend never imports
anything RAG-specific beyond this protocol.
"""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.schemas.rag import RAGRequest, RAGResult


@runtime_checkable
class Retriever(Protocol):
    def search(self, request: RAGRequest) -> Sequence[RAGResult]:
        """Return the most relevant chunks for ``request``, best first."""
        ...
