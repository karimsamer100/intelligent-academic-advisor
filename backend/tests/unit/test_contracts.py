import pytest
from pydantic import ValidationError
from app.schemas.rag import RAGSearchRequest, RAGSearchResponse
from app.rag.models.domain import RetrievedEvidence


def test_request_and_response_contracts():
    req = RAGSearchRequest(query=" What is the maximum credit load? ", regulation=2023, program="CAIE", top_k=5)
    assert req.query == "What is the maximum credit load?"
    response = RAGSearchResponse(results=[RetrievedEvidence(
        chunk_id="C1", text="Evidence", score=0.88, source_id="S1", file_name="Bylaw.pdf",
        page_start=42, page_end=42, section="Registration Rules", document_type="REGULATION",
        regulation=2023, program="CAIE", language="en"
    )])
    assert response.results[0].page_start == 42


def test_blank_query_is_rejected():
    with pytest.raises(ValidationError):
        RAGSearchRequest(query="   ")
