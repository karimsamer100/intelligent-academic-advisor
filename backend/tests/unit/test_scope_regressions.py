import pytest
from app.rag.metadata.enricher import MetadataEnricher
from app.rag.models.domain import ChunkDraft, DocumentMetadata, StoredChunk, RetrievalFilters
from app.rag.repositories.memory_repository import MemoryChunkRepository
from app.rag.validation.validators import validate_chunks, RagValidationError


def source():
    return DocumentMetadata(source_id='scope', file_name='scope.pdf', document_title='Scope',
        document_types=['REGULATION', 'PROCEDURE'], regulations=[2018, 2023], programs=['CAIE', 'CESS'],
        official_status='OFFICIAL', file_hash='a' * 64)


def draft(text, index=1):
    return ChunkDraft(chunk_id=f'scope:{index}', source_id='scope', text=text,
        page_start=1, page_end=1, section='Rules', chunk_index=index, text_hash='b' * 64)


@pytest.mark.parametrize('text,reg,program,kind', [
    ('Regulation 2023 CAIE academic rule', 2023, 'CAIE', 'REGULATION'),
    ('CAIE upload procedure steps', None, 'CAIE', 'PROCEDURE'),
    ('General information', None, None, None),
    ('Regulation 2018 and Regulation 2023; CAIE and CESS procedure', None, None, None),
])
def test_narrow_or_preserve_supported_scope(text, reg, program, kind):
    src = source()
    chunk = MetadataEnricher().enrich(draft(text), src)
    assert chunk.regulation == reg
    assert chunk.applicable_regulations == ([reg] if reg else src.regulations)
    assert chunk.program == program
    assert chunk.applicable_programs == ([program] if program else src.programs)
    assert chunk.document_type == kind
    assert chunk.applicable_document_types == ([kind] if kind else src.document_types)
    validate_chunks([chunk], src)


def test_unscoped_source_does_not_invent_program():
    src = source().model_copy(update={'programs': []})
    chunk = MetadataEnricher().enrich(draft('CAIE procedure'), src)
    assert chunk.program is None
    assert chunk.applicable_programs == []


def test_2018_search_excludes_enriched_2023_chunk():
    src = source()
    chunks = []
    for index, year in enumerate((2018, 2023), 1):
        enriched = MetadataEnricher().enrich(draft(f'Regulation {year} credit load', index), src)
        chunks.append(StoredChunk(**enriched.model_dump(), embedding=[1.0, 0.0],
            embedding_model='fixture', pipeline_version='test', official_status='OFFICIAL'))
    repo = MemoryChunkRepository()
    repo.replace_source(src, chunks)
    results = repo.search([1.0, 0.0], RetrievalFilters(regulation=2018), 5)
    assert [r.regulation for r in results] == [2018]


def test_validation_rejects_stale_broad_applicability():
    src = source()
    chunk = MetadataEnricher().enrich(draft('Regulation 2023'), src)
    chunk.applicable_regulations = [2018, 2023]
    with pytest.raises(RagValidationError, match='applicability_not_narrowed'):
        validate_chunks([chunk], src)
