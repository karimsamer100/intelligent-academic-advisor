from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class DocumentMetadata(BaseModel):
    source_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    document_title: str
    document_types: list[str] = Field(default_factory=list)
    regulations: list[int] = Field(default_factory=list)
    programs: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    effective_year: int | None = None
    version: str | None = None
    official_status: str
    file_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    relative_path: str | None = None
    authority_level: str | None = None
    verification_state: str | None = None
    page_count: int | None = Field(default=None, gt=0)
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class PageText(BaseModel):
    page_number: int = Field(gt=0)
    text: str
    raw_text: str | None = None


class ExtractedDocument(BaseModel):
    source_id: str
    pages: list[PageText]
    extraction_method: str
    extraction_warnings: list[str] = Field(default_factory=list)


class ChunkDraft(BaseModel):
    chunk_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    page_start: int = Field(gt=0)
    page_end: int = Field(gt=0)
    section: str | None = None
    document_type: str | None = None
    regulation: int | None = None
    program: str | None = None
    language: str | None = None
    topic: str | None = None
    chunk_index: int = Field(ge=0)
    text_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    applicable_document_types: list[str] = Field(default_factory=list)
    applicable_regulations: list[int] = Field(default_factory=list)
    applicable_programs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_content(self):
        if not self.text.strip() or self.page_end < self.page_start:
            raise ValueError("empty text or invalid page range")
        return self


class StoredChunk(ChunkDraft):
    embedding: list[float]
    embedding_model: str
    pipeline_version: str
    official_status: str


class RetrievedEvidence(BaseModel):
    chunk_id: str
    text: str
    score: float
    source_id: str
    file_name: str
    page_start: int = Field(gt=0)
    page_end: int = Field(gt=0)
    section: str | None = None
    document_type: str | None = None
    regulation: int | None = None
    program: str | None = None
    language: str | None = None
    topic: str | None = None


class RetrievalFilters(BaseModel):
    regulation: int | None = None
    program: str | None = None
    document_types: list[str] | None = None
    language: str | None = None
    official_status: str | None = None


class SourceState(BaseModel):
    source_id: str
    file_hash: str
    pipeline_version: str
    embedding_model: str
    chunk_count: int = Field(ge=0)
    expected_chunk_count: int | None = Field(default=None, ge=0)


class IngestionResult(BaseModel):
    source_id: str
    status: Literal["INGESTED", "SKIPPED_UNCHANGED"]
    pages_extracted: int = 0
    chunks_created: int = 0
    chunks_inserted: int = 0
    warnings: list[str] = Field(default_factory=list)
    embedding_model: str
    pipeline_version: str
