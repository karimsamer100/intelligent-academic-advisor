import json
import pytest
import fitz
from app.rag.chunkers.section_chunker import SectionAwarePageChunker
from app.rag.cleaners.academic_text_cleaner import AcademicTextCleaner
from app.rag.embeddings.hash_test_provider import HashTestEmbeddingProvider
from app.rag.extractors.pymupdf_extractor import PyMuPDFExtractor
from app.rag.ingestion.pipeline import RagIngestionPipeline
from app.rag.metadata.enricher import MetadataEnricher
from app.rag.models.domain import DocumentMetadata, ChunkDraft
from app.rag.repositories.memory_repository import MemoryChunkRepository
from app.rag.retrieval.service import DocumentSearchService


def source():
    return DocumentMetadata(source_id='test', file_name='test.pdf', document_title='Test',
        document_types=['REGULATION'], regulations=[2018, 2023], programs=[],
        official_status='OFFICIAL', file_hash='a' * 64)


def pipeline(tmp_path):
    return RagIngestionPipeline(PyMuPDFExtractor(), AcademicTextCleaner(), SectionAwarePageChunker(),
        MetadataEnricher(), HashTestEmbeddingProvider(), MemoryChunkRepository(), 'test', True, tmp_path / 'raw')


def test_fresh_pdf_pages_and_raw_debug_preserved(tmp_path):
    path = tmp_path / 'test.pdf'
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), 'Regulation 2023 credit registration requirements')
        pdf.new_page()
        pdf.new_page().insert_text((72, 72), 'Regulation 2018 study duration requirements')
        pdf.save(path)
    ingest = pipeline(tmp_path)
    _, chunks = ingest.prepare_without_embeddings(source(), path)
    debug = json.loads((tmp_path / 'raw/test.json').read_text())
    assert [p['page_number'] for p in debug['pages']] == [1, 2, 3]
    assert debug['extraction_warnings'] == ['empty_page:2']
    assert {c['page_start'] for c in chunks} == {1, 3}
    assert all(c['page_start'] == c['page_end'] for c in chunks)


def test_prepared_import_renarrows_stale_export_and_invalidates_old_version(tmp_path):
    ingest = pipeline(tmp_path)
    chunk = ChunkDraft(chunk_id='test:1', source_id='test', text='Regulation 2023 credit load',
        page_start=1, page_end=1, chunk_index=1, text_hash='b' * 64,
        regulation=2023, applicable_regulations=[2018, 2023])
    assert ingest.ingest_prepared(source(), [chunk]).status == 'INGESTED'
    assert ingest.repository.chunks['test:1'].applicable_regulations == [2023]
    assert chunk.applicable_regulations == [2018, 2023]  # caller data preserved
    assert ingest.pipeline_version == 'test:scope-v2'
    service = DocumentSearchService(ingest.embedder, ingest.repository, min_score=1.01)
    assert service.search_documents('credit load') == []
    with pytest.raises(ValueError, match='top_k'):
        service.search_documents('credit load', top_k=0)
