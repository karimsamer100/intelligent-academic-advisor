"""Where the concrete retriever is wired in.

The RAG task replaces the body of ``get_retriever`` with a real
implementation. Until then no retriever exists, and the RAG endpoint answers
with a clear ``RAG_NOT_CONFIGURED`` error instead of fake data.
"""

from app.rag.interface import Retriever


def get_retriever() -> Retriever | None:
    return None
