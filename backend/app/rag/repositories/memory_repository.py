from __future__ import annotations

import math
from app.rag.models.domain import DocumentMetadata, RetrievedEvidence, RetrievalFilters, SourceState, StoredChunk
from app.rag.repositories.base import ChunkRepository


class MemoryChunkRepository(ChunkRepository):
    """Test repository that mirrors strict metadata-filter behavior without PostgreSQL."""

    def __init__(self) -> None:
        self.sources: dict[str, tuple[DocumentMetadata, str, str]] = {}
        self.chunks: dict[str, StoredChunk] = {}

    def get_source_state(self, source_id: str) -> SourceState | None:
        if source_id not in self.sources:
            return None
        source, pipeline_version, embedding_model = self.sources[source_id]
        count = sum(1 for c in self.chunks.values() if c.source_id == source_id)
        return SourceState(
            source_id=source_id,
            file_hash=source.file_hash,
            pipeline_version=pipeline_version,
            embedding_model=embedding_model,
            chunk_count=count,
            expected_chunk_count=count,
        )

    def replace_source(self, source: DocumentMetadata, chunks: list[StoredChunk]) -> int:
        self.chunks = {k: v for k, v in self.chunks.items() if v.source_id != source.source_id}
        for chunk in chunks:
            if chunk.chunk_id in self.chunks:
                raise ValueError(f"duplicate_chunk_id:{chunk.chunk_id}")
            self.chunks[chunk.chunk_id] = chunk
        if chunks:
            self.sources[source.source_id] = (source, chunks[0].pipeline_version, chunks[0].embedding_model)
        return len(chunks)

    def search(self, query_embedding, filters, top_k, min_score=None):
        candidates: list[tuple[float, StoredChunk, DocumentMetadata]] = []
        for chunk in self.chunks.values():
            if filters.regulation is not None and filters.regulation not in chunk.applicable_regulations:
                continue
            if filters.program is not None and filters.program not in chunk.applicable_programs:
                continue
            if filters.document_types and not any(t in chunk.applicable_document_types for t in filters.document_types):
                continue
            if filters.language and chunk.language != filters.language:
                continue
            if filters.official_status and chunk.official_status != filters.official_status:
                continue
            score = self._cosine(query_embedding, chunk.embedding)
            if min_score is not None and score < min_score:
                continue
            candidates.append((score, chunk, self.sources[chunk.source_id][0]))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [
            RetrievedEvidence(
                chunk_id=c.chunk_id,
                text=c.text,
                score=score,
                source_id=c.source_id,
                file_name=source.file_name,
                page_start=c.page_start,
                page_end=c.page_end,
                section=c.section,
                document_type=c.document_type,
                regulation=c.regulation,
                program=c.program,
                language=c.language,
                topic=c.topic,
            )
            for score, c, source in candidates[:top_k]
        ]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (na * nb)
