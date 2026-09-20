from app.api.deps import get_rag_service
from app.schemas.rag import RAGRequest, RAGResult
from app.services.rag_service import RAGService


class StubRetriever:
    """Test double standing in for the future RAG module."""

    def __init__(self, count=2):
        self.count = count
        self.received: RAGRequest | None = None

    def search(self, request: RAGRequest):
        self.received = request
        return [
            RAGResult(chunk_id=f"CHK-{i}", text=f"chunk {i}", score=1 - i / 100, source_id="SRC-001")
            for i in range(self.count)
        ]


def test_rag_search_without_a_retriever_is_a_clean_501(client):
    response = client.post("/api/v1/rag/search", json={"query": "What is the maximum credit load?"})
    assert response.status_code == 501
    error = response.json()["error"]
    assert error["code"] == "RAG_NOT_CONFIGURED"
    assert error["details"] is None


def test_rag_search_delegates_to_the_retriever(app, client):
    retriever = StubRetriever(count=2)
    app.dependency_overrides[get_rag_service] = lambda: RAGService(retriever=retriever)

    payload = {"query": "credit load", "regulation": 23, "program": "CAIE", "document_types": ["REGULATION"], "top_k": 5}
    response = client.post("/api/v1/rag/search", json=payload)

    assert response.status_code == 200
    assert [r["chunk_id"] for r in response.json()["results"]] == ["CHK-0", "CHK-1"]
    # The retriever received the validated contract object, unchanged.
    assert retriever.received.regulation == 23
    assert retriever.received.program == "CAIE"
    assert retriever.received.document_types == ["REGULATION"]


def test_rag_service_enforces_top_k(app, client):
    app.dependency_overrides[get_rag_service] = lambda: RAGService(retriever=StubRetriever(count=10))
    response = client.post("/api/v1/rag/search", json={"query": "q", "top_k": 3})
    assert response.status_code == 200
    assert len(response.json()["results"]) == 3


def test_rag_search_validation_error_uses_the_standard_format(client):
    response = client.post("/api/v1/rag/search", json={"query": "", "top_k": 0})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert isinstance(error["details"], list) and error["details"]
    # Submitted input is never echoed back.
    assert all("input" not in item for item in error["details"])
