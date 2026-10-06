"""Read-only official-document search tool adapter."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.rag import RAGRequest
from app.services.rag_service import RAGService
from app.planning.repositories.student_repository import StudentRepository
from app.tools.context import ToolExecutionContext, resolve_student_state
from app.tools.interface import AcademicTool


class SearchOfficialDocumentsArguments(BaseModel):
    """LLM-controlled search text and non-trusted narrowing filters."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1)
    document_types: list[str] | None = None

    @field_validator("document_types")
    @classmethod
    def _reject_blank_document_types(
        cls, value: list[str] | None
    ) -> list[str] | None:
        if value is not None and any(not item.strip() for item in value):
            raise ValueError("document_types must not contain blank values")
        return value


class SearchOfficialDocumentsTool(AcademicTool[SearchOfficialDocumentsArguments]):
    name = "search_official_documents"
    description = "Search official academic documents for relevant evidence."
    arguments_model = SearchOfficialDocumentsArguments

    def __init__(
        self,
        student_repository: StudentRepository,
        rag_service: RAGService,
    ) -> None:
        self._student_repository = student_repository
        self._rag_service = rag_service

    def _execute(
        self,
        arguments: SearchOfficialDocumentsArguments,
        trusted_context: ToolExecutionContext,
    ) -> dict[str, Any]:
        student_id = None
        regulation = None
        program = None
        if trusted_context.student_id is not None:
            student = resolve_student_state(
                trusted_context,
                self._student_repository,
                self.name,
            )
            student_id = student.student_id
            regulation = student.regulation.year
            program = str(student.program)

        request = RAGRequest(
            query=arguments.query,
            student_id=student_id,
            regulation=regulation,
            program=program,
            document_types=arguments.document_types,
        )
        response = self._rag_service.search(request)
        return response.model_dump(mode="json")


__all__ = [
    "SearchOfficialDocumentsArguments",
    "SearchOfficialDocumentsTool",
]
