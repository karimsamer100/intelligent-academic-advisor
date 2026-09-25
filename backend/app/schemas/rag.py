"""Shared RAG contracts.

These are the only types the backend needs to know about RAG: a request
going in, ranked chunks coming out. How chunks are extracted, embedded or
searched is entirely the RAG module's business.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import get_settings


def _default_top_k() -> int:
    return get_settings().rag_top_k


def _check_page_order(page_start: int | None, page_end: int | None) -> None:
    if page_start is not None and page_end is not None and page_end < page_start:
        raise ValueError("page_end must be greater than or equal to page_start")


# --------------------------------------------------------------------------
# Request / response
# --------------------------------------------------------------------------
class RAGRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "query": "What is the maximum credit load?",
                    "student_id": None,
                    "regulation": 23,
                    "program": "CAIE",
                    "document_types": ["REGULATION"],
                    "language": "en",
                    "top_k": 5,
                }
            ]
        },
    )

    query: str = Field(min_length=1)
    # Trusted profile context (when available) should be preferred over
    # anything inferred from the free-text query.
    student_id: str | None = None
    regulation: int | None = Field(default=None, gt=0)
    program: str | None = None
    document_types: list[str] | None = None
    language: str | None = None
    official_status: str | None = None
    top_k: int = Field(default_factory=_default_top_k, gt=0)

    @field_validator("document_types")
    @classmethod
    def _no_blank_document_types(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and any(not item.strip() for item in value):
            raise ValueError("document_types must not contain blank values")
        return value

    @field_validator("top_k")
    @classmethod
    def _top_k_within_configured_max(cls, value: int) -> int:
        maximum = get_settings().rag_max_top_k
        if value > maximum:
            raise ValueError(f"top_k must be less than or equal to {maximum}")
        return value


class RAGResult(BaseModel):
    chunk_id: str
    text: str
    score: float
    source_id: str
    file_name: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section: str | None = None
    document_type: str | None = None
    regulation: int | None = None
    program: str | None = None
    language: str | None = None

    @model_validator(mode="after")
    def _validate_pages(self) -> "RAGResult":
        _check_page_order(self.page_start, self.page_end)
        return self


class RAGResponse(BaseModel):
    results: list[RAGResult] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Shared metadata (used by the RAG module when it indexes documents)
# --------------------------------------------------------------------------
class DocumentMetadata(BaseModel):
    """Document-level metadata. A document may have several of each list field."""

    source_id: str
    file_name: str
    document_title: str | None = None
    document_types: list[str] = Field(default_factory=list)
    regulations: list[int] = Field(default_factory=list)
    programs: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    effective_year: int | None = None
    version: str | None = None
    official_status: str | None = None
    file_hash: str | None = None


class ChunkMetadata(BaseModel):
    """Chunk-level metadata; narrows the document scope where possible."""

    chunk_id: str
    source_id: str
    text: str
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section: str | None = None
    document_type: str | None = None
    regulation: int | None = None
    program: str | None = None
    language: str | None = None
    topic: str | None = None
    chunk_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_pages(self) -> "ChunkMetadata":
        _check_page_order(self.page_start, self.page_end)
        return self


__all__ = [
    "ChunkMetadata",
    "DocumentMetadata",
    "RAGRequest",
    "RAGResponse",
    "RAGResult",
]
