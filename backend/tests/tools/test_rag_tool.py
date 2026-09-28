from __future__ import annotations

import json

import pytest

from app.planning.repositories.adapters.student_json_repository import (
    JsonStudentRepository,
)
from app.schemas.rag import RAGRequest, RAGResponse, RAGResult
from app.tools.context import ToolExecutionContext
from app.tools.errors import ToolArgumentValidationError, ToolDataUnavailableError
from app.tools.rag import SearchOfficialDocumentsTool


def _student_repository(tmp_path) -> JsonStudentRepository:
    path = tmp_path / "students.json"
    path.write_text(
        json.dumps(
            {
                "students": [
                    {
                        "student_id": "student-001",
                        "regulation": 2023,
                        "program": "CAIE",
                        "course_attempts": [],
                        "current_registrations": [],
                        "academic_snapshot": {
                            "student_id": "student-001",
                            "regulation": 2023,
                            "program": "CAIE",
                            "gpa": 3.0,
                            "earned_credit_hours": 0,
                        },
                        "history_coverage": "COMPLETE",
                        "registration_coverage": "COMPLETE",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return JsonStudentRepository(path)


class RecordingRAGService:
    def __init__(self) -> None:
        self.requests: list[RAGRequest] = []

    def search(self, request: RAGRequest) -> RAGResponse:
        self.requests.append(request)
        return RAGResponse(
            results=[
                RAGResult(
                    chunk_id="chunk-1",
                    text="official result",
                    score=0.9,
                    source_id="source-1",
                )
            ]
        )


def test_rag_tool_definition_contains_only_llm_search_fields(tmp_path) -> None:
    tool = SearchOfficialDocumentsTool(_student_repository(tmp_path), RecordingRAGService())

    properties = tool.definition.input_schema["properties"]

    assert set(properties) == {"query", "document_types", "language"}
    assert "student_id" not in properties
    assert "regulation" not in properties
    assert "program" not in properties
    assert "top_k" not in properties


def test_rag_tool_injects_trusted_student_filters(tmp_path) -> None:
    rag = RecordingRAGService()
    tool = SearchOfficialDocumentsTool(_student_repository(tmp_path), rag)

    result = tool.execute(
        {"query": "maximum credit load", "document_types": ["REGULATION"]},
        ToolExecutionContext(student_id="student-001"),
    )

    request = rag.requests[0]
    assert request.student_id == "student-001"
    assert request.regulation == 2023
    assert request.program == "CAIE"
    assert request.document_types == ["REGULATION"]
    assert result["results"][0]["chunk_id"] == "chunk-1"


def test_rag_tool_allows_general_search_without_student_context(tmp_path) -> None:
    rag = RecordingRAGService()
    tool = SearchOfficialDocumentsTool(_student_repository(tmp_path), rag)

    tool.execute({"query": "maximum credit load", "language": "en"}, ToolExecutionContext())

    request = rag.requests[0]
    assert request.student_id is None
    assert request.regulation is None
    assert request.program is None
    assert request.language == "en"


def test_rag_tool_rejects_llm_trusted_filter_overrides(tmp_path) -> None:
    rag = RecordingRAGService()
    tool = SearchOfficialDocumentsTool(_student_repository(tmp_path), rag)

    with pytest.raises(ToolArgumentValidationError):
        tool.execute(
            {
                "query": "maximum credit load",
                "student_id": "forged-student",
                "regulation": 2018,
                "program": "CESS",
                "top_k": 20,
            },
            ToolExecutionContext(student_id="student-001"),
        )

    assert rag.requests == []


def test_rag_tool_fails_closed_when_trusted_student_is_missing(tmp_path) -> None:
    rag = RecordingRAGService()
    tool = SearchOfficialDocumentsTool(_student_repository(tmp_path), rag)

    with pytest.raises(ToolDataUnavailableError):
        tool.execute(
            {"query": "maximum credit load"},
            ToolExecutionContext(student_id="missing-student"),
        )

    assert rag.requests == []
