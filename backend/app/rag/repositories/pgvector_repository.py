from __future__ import annotations

import logging
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from app.rag.models.domain import DocumentMetadata, RetrievedEvidence, RetrievalFilters, SourceState, StoredChunk
from app.rag.models.orm import RagChunk, RagSource
from app.rag.repositories.base import ChunkRepository

logger = logging.getLogger(__name__)


class PgVectorChunkRepository(ChunkRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_source_state(self, source_id: str) -> SourceState | None:
        source = self.session.get(RagSource, source_id)
        if source is None:
            return None
        count = self.session.scalar(select(func.count()).select_from(RagChunk).where(RagChunk.source_id == source_id)) or 0
        return SourceState(
            source_id=source_id,
            file_hash=source.file_hash,
            pipeline_version=source.pipeline_version,
            embedding_model=source.embedding_model,
            chunk_count=int(count),
            expected_chunk_count=source.expected_chunk_count,
        )

    def replace_source(self, source: DocumentMetadata, chunks: list[StoredChunk]) -> int:
        if not chunks:
            raise ValueError("cannot insert a source with zero chunks")

        source_values = {
            "source_id": source.source_id,
            "file_name": source.file_name,
            "document_title": source.document_title,
            "document_types": source.document_types,
            "regulations": source.regulations,
            "programs": source.programs,
            "languages": source.languages,
            "effective_year": source.effective_year,
            "version": source.version,
            "official_status": source.official_status,
            "file_hash": source.file_hash,
            "relative_path": source.relative_path,
            "authority_level": source.authority_level,
            "verification_state": source.verification_state,
            "page_count": source.page_count,
            "source_metadata": source.source_metadata,
            "embedding_model": chunks[0].embedding_model,
            "pipeline_version": chunks[0].pipeline_version,
            "expected_chunk_count": len(chunks),
        }
        stmt = insert(RagSource).values(**source_values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[RagSource.source_id],
            set_={key: value for key, value in source_values.items() if key != "source_id"},
        )
        self.session.execute(stmt)
        self.session.execute(delete(RagChunk).where(RagChunk.source_id == source.source_id))
        self.session.flush()

        rows = [
            RagChunk(
                chunk_id=c.chunk_id,
                source_id=c.source_id,
                text=c.text,
                text_hash=c.text_hash,
                embedding=c.embedding,
                page_start=c.page_start,
                page_end=c.page_end,
                section=c.section,
                document_type=c.document_type,
                regulation=c.regulation,
                program=c.program,
                language=c.language,
                topic=c.topic,
                chunk_index=c.chunk_index,
                applicable_document_types=c.applicable_document_types,
                applicable_regulations=c.applicable_regulations,
                applicable_programs=c.applicable_programs,
                official_status=c.official_status,
                embedding_model=c.embedding_model,
                pipeline_version=c.pipeline_version,
                chunk_metadata=c.metadata,
            )
            for c in chunks
        ]
        self.session.add_all(rows)
        self.session.flush()
        logger.info("Chunks inserted", extra={"source_id": source.source_id, "chunk_count": len(rows)})
        return len(rows)

    def search(
        self,
        query_embedding: list[float],
        filters: RetrievalFilters,
        top_k: int,
        min_score: float | None = None,
    ) -> list[RetrievedEvidence]:
        distance = RagChunk.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(RagChunk, RagSource.file_name, distance)
            .join(RagSource, RagSource.source_id == RagChunk.source_id)
        )

        # Trusted scope is enforced at SQL level. Applicability arrays come only from explicit source/chunk metadata.
        if filters.regulation is not None:
            stmt = stmt.where(RagChunk.applicable_regulations.contains([filters.regulation]))
        if filters.program is not None:
            stmt = stmt.where(RagChunk.applicable_programs.contains([filters.program]))
        if filters.document_types:
            stmt = stmt.where(RagChunk.applicable_document_types.overlap(filters.document_types))
        if filters.language:
            stmt = stmt.where(RagChunk.language == filters.language)
        if filters.official_status:
            stmt = stmt.where(RagChunk.official_status == filters.official_status)

        stmt = stmt.order_by(distance.asc()).limit(top_k)
        rows = self.session.execute(stmt).all()
        results: list[RetrievedEvidence] = []
        for chunk, file_name, raw_distance in rows:
            score = 1.0 - float(raw_distance)
            if min_score is not None and score < min_score:
                continue
            results.append(
                RetrievedEvidence(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    score=score,
                    source_id=chunk.source_id,
                    file_name=file_name,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section=chunk.section,
                    document_type=chunk.document_type,
                    regulation=chunk.regulation,
                    program=chunk.program,
                    language=chunk.language,
                    topic=chunk.topic,
                )
            )
        return results
