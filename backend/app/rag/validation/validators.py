from __future__ import annotations
from collections import Counter
from app.rag.models.domain import ChunkDraft, DocumentMetadata, ExtractedDocument, StoredChunk


class RagValidationError(ValueError):
    pass


def validate_extracted(document: ExtractedDocument) -> list[str]:
    if not document.pages:
        raise RagValidationError("empty_document")
    warnings = []
    for page in document.pages:
        if not page.text.strip():
            warnings.append(f"empty_page:{page.page_number}")
    if len(warnings) == len(document.pages):
        raise RagValidationError("all_pages_empty")
    return warnings


def validate_chunks(chunks: list[ChunkDraft], source: DocumentMetadata) -> None:
    if not chunks:
        raise RagValidationError("no_chunks")
    ids = Counter(c.chunk_id for c in chunks)
    dupes = [cid for cid, count in ids.items() if count > 1]
    if dupes:
        raise RagValidationError(f"duplicate_chunk_id:{dupes[0]}")
    for chunk in chunks:
        if not chunk.source_id:
            raise RagValidationError("missing_source_id")
        if not chunk.text.strip():
            raise RagValidationError(f"empty_chunk:{chunk.chunk_id}")
        if chunk.page_start <= 0 or chunk.page_end < chunk.page_start:
            raise RagValidationError(f"missing_or_invalid_page_metadata:{chunk.chunk_id}")
        if len(source.regulations) == 1 and chunk.regulation is None:
            raise RagValidationError(f"missing_regulation_on_regulation_specific_chunk:{chunk.chunk_id}")


def validate_embeddings(chunks: list[StoredChunk], dimension: int) -> None:
    for chunk in chunks:
        if len(chunk.embedding) != dimension:
            raise RagValidationError(
                f"embedding_dimension_mismatch:{chunk.chunk_id}:got={len(chunk.embedding)}:expected={dimension}"
            )
