from pathlib import Path
from app.rag.chunkers.section_chunker import SectionAwarePageChunker
from app.rag.cleaners.academic_text_cleaner import AcademicTextCleaner
from app.rag.embeddings.hash_test_provider import HashTestEmbeddingProvider
from app.rag.extractors.base import DocumentExtractor
from app.rag.ingestion.pipeline import RagIngestionPipeline
from app.rag.metadata.enricher import MetadataEnricher
from app.rag.models.domain import DocumentMetadata, ExtractedDocument, PageText
from app.rag.repositories.memory_repository import MemoryChunkRepository


class FixtureExtractor(DocumentExtractor):
    def extract(self, path: Path, source_id: str):
        return ExtractedDocument(
            source_id=source_id,
            extraction_method="fixture",
            pages=[PageText(page_number=1, text="Course Registration Rules\nStudents may register credit hours according to the published rule. " * 5)],
        )


def test_reingesting_unchanged_source_is_skipped():
    source = DocumentMetadata(
        source_id="SRC23",
        file_name="x.pdf",
        document_title="X",
        document_types=["Full Academic Regulation"],
        regulations=[2023],
        programs=["CAIE"],
        official_status="OFFICIAL",
        file_hash="f" * 64,
    )
    repo = MemoryChunkRepository()
    embedder = HashTestEmbeddingProvider(64)
    pipeline = RagIngestionPipeline(
        extractor=FixtureExtractor(),
        cleaner=AcademicTextCleaner(),
        chunker=SectionAwarePageChunker(300, 30, 40),
        enricher=MetadataEnricher(),
        embedder=embedder,
        repository=repo,
        pipeline_version="rag-test-v1",
    )
    first = pipeline.ingest(source, Path("ignored.pdf"))
    second = pipeline.ingest(source, Path("ignored.pdf"))
    assert first.status == "INGESTED"
    assert second.status == "SKIPPED_UNCHANGED"
    assert len(repo.chunks) == first.chunks_inserted
