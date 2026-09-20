import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.rag import ChunkMetadata, DocumentMetadata, RAGRequest, RAGResponse, RAGResult

VALID_REQUEST = {
    "query": "What is the maximum credit load?",
    "student_id": None,
    "regulation": 23,
    "program": "CAIE",
    "document_types": ["REGULATION"],
    "language": "en",
    "top_k": 5,
}

VALID_RESULT = {
    "chunk_id": "CHK-001",
    "text": "...",
    "score": 0.88,
    "source_id": "SRC-001",
    "file_name": "Bylaw 2023.pdf",
    "page_start": 42,
    "page_end": 42,
    "section": "Registration Rules",
    "document_type": "REGULATION",
    "regulation": 23,
    "program": "CAIE",
    "language": "en",
}


# ---- request ---------------------------------------------------------------
def test_request_accepts_the_documented_example():
    request = RAGRequest(**VALID_REQUEST)
    assert request.query == "What is the maximum credit load?"
    assert request.regulation == 23
    assert request.document_types == ["REGULATION"]


def test_request_only_needs_a_query_and_defaults_top_k_from_settings():
    request = RAGRequest(query="hello")
    assert request.student_id is None
    assert request.regulation is None
    assert request.document_types is None
    assert request.top_k == get_settings().rag_top_k


def test_query_is_trimmed():
    assert RAGRequest(query="  hello  ").query == "hello"


@pytest.mark.parametrize("query", ["", "   "])
def test_blank_query_is_rejected(query):
    with pytest.raises(ValidationError):
        RAGRequest(query=query)


def test_query_is_required():
    with pytest.raises(ValidationError):
        RAGRequest()


@pytest.mark.parametrize("top_k", [0, -1])
def test_top_k_must_be_positive(top_k):
    with pytest.raises(ValidationError):
        RAGRequest(query="q", top_k=top_k)


def test_regulation_must_be_a_positive_integer():
    with pytest.raises(ValidationError):
        RAGRequest(query="q", regulation=0)
    with pytest.raises(ValidationError):
        RAGRequest(query="q", regulation="twenty-three")


def test_blank_document_type_is_rejected():
    with pytest.raises(ValidationError):
        RAGRequest(query="q", document_types=["REGULATION", " "])


def test_unknown_request_fields_are_rejected():
    with pytest.raises(ValidationError):
        RAGRequest(query="q", topk=3)


# ---- response --------------------------------------------------------------
def test_response_accepts_the_documented_example():
    response = RAGResponse(results=[VALID_RESULT])
    assert response.results[0].chunk_id == "CHK-001"
    assert response.results[0].score == pytest.approx(0.88)


def test_response_can_be_empty():
    assert RAGResponse().results == []


def test_result_only_requires_core_fields():
    result = RAGResult(chunk_id="c", text="t", score=0.1, source_id="s")
    assert result.file_name is None
    assert result.page_start is None


@pytest.mark.parametrize("missing", ["chunk_id", "text", "score", "source_id"])
def test_result_required_fields(missing):
    data = {k: v for k, v in VALID_RESULT.items() if k != missing}
    with pytest.raises(ValidationError):
        RAGResult(**data)


def test_result_score_must_be_numeric():
    with pytest.raises(ValidationError):
        RAGResult(**{**VALID_RESULT, "score": "high"})


def test_result_page_range_must_be_ordered():
    with pytest.raises(ValidationError):
        RAGResult(**{**VALID_RESULT, "page_start": 10, "page_end": 9})


# ---- shared metadata -------------------------------------------------------
def test_document_metadata_supports_multiple_values():
    doc = DocumentMetadata(
        source_id="SRC-001",
        file_name="Bylaw.pdf",
        document_types=["REGULATION", "BYLAW"],
        regulations=[18, 23],
        programs=["CAIE", "CSE"],
        languages=["en", "ar"],
    )
    assert doc.regulations == [18, 23]
    assert doc.languages == ["en", "ar"]


def test_chunk_metadata_validates_pages():
    ChunkMetadata(chunk_id="c", source_id="s", text="t", page_start=1, page_end=2, chunk_index=0)
    with pytest.raises(ValidationError):
        ChunkMetadata(chunk_id="c", source_id="s", text="t", page_start=5, page_end=2)
