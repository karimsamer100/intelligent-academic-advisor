from __future__ import annotations

import json
import logging
from pathlib import Path
from app.rag.chunkers.base import Chunker
from app.rag.cleaners.base import TextCleaner
from app.rag.embeddings.base import EmbeddingProvider
from app.rag.extractors.base import DocumentExtractor
from app.rag.metadata.enricher import MetadataEnricher
from app.rag.models.domain import DocumentMetadata, IngestionResult, StoredChunk
from app.rag.repositories.base import ChunkRepository
from app.rag.validation.validators import validate_chunks, validate_embeddings, validate_extracted

logger = logging.getLogger(__name__)


class RagIngestionPipeline:
    def __init__(
        self,
        extractor: DocumentExtractor,
        cleaner: TextCleaner,
        chunker: Chunker,
        enricher: MetadataEnricher,
        embedder: EmbeddingProvider,
        repository: ChunkRepository,
        pipeline_version: str,
        preserve_raw_extraction: bool = False,
        raw_extract_dir: Path | None = None,
    ) -> None:
        self.extractor = extractor
        self.cleaner = cleaner
        self.chunker = chunker
        self.enricher = enricher
        self.embedder = embedder
        self.repository = repository
        self.pipeline_version = pipeline_version
        self.preserve_raw_extraction = preserve_raw_extraction
        self.raw_extract_dir = raw_extract_dir

    def ingest(self, source: DocumentMetadata, extraction_input: Path) -> IngestionResult:
        logger.info("Source loaded", extra={"source_id": source.source_id})
        state = self.repository.get_source_state(source.source_id)
        if (
            state
            and state.file_hash == source.file_hash
            and state.pipeline_version == self.pipeline_version
            and state.embedding_model == self.embedder.model_name
            and state.chunk_count > 0
            and (state.expected_chunk_count is None or state.chunk_count == state.expected_chunk_count)
        ):
            logger.info("Unchanged source already ingested; skipping", extra={"source_id": source.source_id})
            return IngestionResult(
                source_id=source.source_id,
                status="SKIPPED_UNCHANGED",
                chunks_inserted=0,
                embedding_model=self.embedder.model_name,
                pipeline_version=self.pipeline_version,
            )

        try:
            extracted = self.extractor.extract(extraction_input, source.source_id)
            validation_warnings = validate_extracted(extracted)
            logger.info("Pages extracted", extra={"source_id": source.source_id, "page_count": len(extracted.pages)})
            if self.preserve_raw_extraction and self.raw_extract_dir:
                self._write_debug_extract(extracted)
            cleaned = self.cleaner.clean(extracted)
            drafts = self.chunker.chunk(cleaned, source)
            drafts = [self.enricher.enrich(chunk, source) for chunk in drafts]
            validate_chunks(drafts, source)
            logger.info("Chunks created", extra={"source_id": source.source_id, "chunk_count": len(drafts)})

            inferred_languages = sorted({c.language for c in drafts if c.language and c.language != "und"})
            if inferred_languages:
                source.languages = inferred_languages
            source.page_count = source.page_count or len(extracted.pages)

            logger.info("Generating embeddings", extra={"source_id": source.source_id, "chunk_count": len(drafts)})
            vectors = self.embedder.embed_documents([c.text for c in drafts])
            if len(vectors) != len(drafts):
                raise RuntimeError("embedding_failure:provider_return_count_mismatch")

            stored = [
                StoredChunk(
                    **draft.model_dump(),
                    embedding=vector,
                    embedding_model=self.embedder.model_name,
                    pipeline_version=self.pipeline_version,
                    official_status=source.official_status,
                )
                for draft, vector in zip(drafts, vectors)
            ]
            validate_embeddings(stored, self.embedder.dimension)
            inserted = self.repository.replace_source(source, stored)
            logger.info("Source ingestion complete", extra={"source_id": source.source_id, "chunk_count": inserted})
            return IngestionResult(
                source_id=source.source_id,
                status="INGESTED",
                pages_extracted=len(extracted.pages),
                chunks_created=len(drafts),
                chunks_inserted=inserted,
                warnings=sorted(set(extracted.extraction_warnings + validation_warnings)),
                embedding_model=self.embedder.model_name,
                pipeline_version=self.pipeline_version,
            )
        except Exception:
            logger.exception("Source ingestion failed", extra={"source_id": source.source_id})
            raise

    def ingest_prepared(self, source: DocumentMetadata, drafts) -> IngestionResult:
        """Embed and store a validated prepared chunk export without re-extracting PDFs."""
        state = self.repository.get_source_state(source.source_id)
        if (
            state
            and state.file_hash == source.file_hash
            and state.pipeline_version == self.pipeline_version
            and state.embedding_model == self.embedder.model_name
            and state.chunk_count > 0
            and (state.expected_chunk_count is None or state.chunk_count == state.expected_chunk_count)
        ):
            return IngestionResult(
                source_id=source.source_id,
                status="SKIPPED_UNCHANGED",
                chunks_inserted=0,
                embedding_model=self.embedder.model_name,
                pipeline_version=self.pipeline_version,
            )

        drafts = list(drafts)
        validate_chunks(drafts, source)
        vectors = self.embedder.embed_documents([c.text for c in drafts])
        if len(vectors) != len(drafts):
            raise RuntimeError("embedding_failure:provider_return_count_mismatch")
        stored = [
            StoredChunk(
                **draft.model_dump(),
                embedding=vector,
                embedding_model=self.embedder.model_name,
                pipeline_version=self.pipeline_version,
                official_status=source.official_status,
            )
            for draft, vector in zip(drafts, vectors)
        ]
        validate_embeddings(stored, self.embedder.dimension)
        inserted = self.repository.replace_source(source, stored)
        return IngestionResult(
            source_id=source.source_id,
            status="INGESTED",
            chunks_created=len(drafts),
            chunks_inserted=inserted,
            embedding_model=self.embedder.model_name,
            pipeline_version=self.pipeline_version,
        )

    def prepare_without_embeddings(self, source: DocumentMetadata, extraction_input: Path) -> tuple[DocumentMetadata, list[dict]]:
        """Validation/inspection path used to review chunk quality before vector ingestion."""
        extracted = self.extractor.extract(extraction_input, source.source_id)
        validate_extracted(extracted)
        cleaned = self.cleaner.clean(extracted)
        drafts = [self.enricher.enrich(c, source) for c in self.chunker.chunk(cleaned, source)]
        validate_chunks(drafts, source)
        source.languages = sorted({c.language for c in drafts if c.language and c.language != "und"})
        source.page_count = source.page_count or len(extracted.pages)
        return source, [c.model_dump() for c in drafts]

    def _write_debug_extract(self, document) -> None:
        self.raw_extract_dir.mkdir(parents=True, exist_ok=True)
        target = self.raw_extract_dir / f"{document.source_id}.json"
        target.write_text(document.model_dump_json(indent=2), encoding="utf-8")
