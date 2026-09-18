from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.rag.models.domain import RetrievedEvidence


class RAGSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    student_id: str | None = None
    regulation: int | None = None
    program: str | None = None
    document_types: list[str] | None = None
    language: str | None = None
    official_status: str | None = None
    top_k: int = Field(default=5, gt=0, le=20)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value

    @field_validator("regulation")
    @classmethod
    def normalize_regulation(cls, value: int | None) -> int | None:
        # Project material uses both short labels (18/23) and full years (2018/2023).
        if value == 18:
            return 2018
        if value == 23:
            return 2023
        return value

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else value

    @field_validator("program")
    @classmethod
    def normalize_program(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class RAGSearchResponse(BaseModel):
    results: list[RetrievedEvidence]
