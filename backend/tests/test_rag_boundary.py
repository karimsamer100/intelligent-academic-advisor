from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.rag.models.domain import RetrievedEvidence
from app.schemas.rag import RAGRequest


class RecordingSearchService:
    def __init__(self, evidence: list[RetrievedEvidence]) -> None:
        self.evidence = evidence
        self.calls: list[dict] = []

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
        self.calls.append(
            {
                "query": query,
                "regulation": regulation,
                "program": program,
                "document_types": document_types,
                "language": language,
                "official_status": official_status,
                "top_k": top_k,
            }
        )
        return self.evidence


def _evidence() -> list[RetrievedEvidence]:
    return [
        RetrievedEvidence(
            chunk_id="chunk-1",
            text="first evidence",
            score=0.91,
            source_id="source-1",
            file_name="rules.pdf",
            page_start=4,
            page_end=5,
            section="Load rules",
            document_type="REGULATION",
            regulation=2023,
            program="CAIE",
            language="en",
            topic="credit_load",
        ),
        RetrievedEvidence(
            chunk_id="chunk-2",
            text="second evidence",
            score=0.72,
            source_id="source-1",
            file_name="rules.pdf",
            page_start=8,
            page_end=8,
            section="Exceptions",
            document_type="REGULATION",
            regulation=2023,
            program="CAIE",
            language="en",
            topic="credit_load",
        ),
    ]


def test_pgvector_retriever_delegates_filters_and_maps_ranked_evidence() -> None:
    from app.rag.retriever import PgVectorRetriever

    search_service = RecordingSearchService(_evidence())
    retriever = PgVectorRetriever(search_service)
    request = RAGRequest(
        query="maximum credit load",
        regulation=23,
        program="CAIE",
        document_types=["REGULATION"],
        language="en",
        official_status="official",
        top_k=2,
    )

    results = list(retriever.search(request))

    assert [result.chunk_id for result in results] == ["chunk-1", "chunk-2"]
    assert results[0].model_dump() == {
        "chunk_id": "chunk-1",
        "text": "first evidence",
        "score": 0.91,
        "source_id": "source-1",
        "file_name": "rules.pdf",
        "page_start": 4,
        "page_end": 5,
        "section": "Load rules",
        "document_type": "REGULATION",
        "regulation": 2023,
        "program": "CAIE",
        "language": "en",
    }
    assert search_service.calls == [
        {
            "query": "maximum credit load",
            "regulation": 2023,
            "program": "CAIE",
            "document_types": ["REGULATION"],
            "language": "en",
            "official_status": "official",
            "top_k": 2,
        }
    ]


@pytest.mark.parametrize(
    ("input_value", "expected"),
    [(18, 2018), (23, 2023), (2018, 2018), (2023, 2023), (None, None)],
)
def test_rag_regulation_normalization(input_value: int | None, expected: int | None) -> None:
    from app.rag.retriever import normalize_regulation

    assert normalize_regulation(input_value) == expected


def test_rag_request_rejects_top_k_above_configured_max() -> None:
    settings = get_settings()

    with pytest.raises(ValidationError):
        RAGRequest(query="credit load", top_k=settings.rag_max_top_k + 1)
