"""Opt-in tests run the real migration in a transaction-isolated schema."""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import Session
from app.rag.models.domain import DocumentMetadata, ChunkDraft, StoredChunk, RetrievalFilters
from app.rag.models.orm import RagSource, RagChunk
from app.rag.repositories.pgvector_repository import PgVectorChunkRepository
from app.rag.metadata.enricher import MetadataEnricher
from app.rag.ingestion.pipeline import RagIngestionPipeline
from app.rag.embeddings.hash_test_provider import HashTestEmbeddingProvider

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv('RUN_PGVECTOR_TESTS') != '1', reason='Set RUN_PGVECTOR_TESTS=1 to run live PostgreSQL tests')]


@pytest.fixture
def repo(monkeypatch):
    # conftest defaults DATABASE_URL to SQLite for API tests; never use it here.
    url = os.getenv('PGVECTOR_TEST_DATABASE_URL') or os.getenv('DATABASE_URL', '')
    if not url or url.startswith('sqlite'):
        url = 'postgresql+psycopg://advisor:advisor@localhost:5432/advisor'
    engine = create_engine(url)
    schema = 'rag_test_' + uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            monkeypatch.setenv('EMBEDDING_DIMENSION', str(RagChunk.embedding.type.dim))
            path = Path(__file__).resolve().parents[2] / 'alembic/versions/0001_rag_pgvector.py'
            spec = importlib.util.spec_from_file_location('rag_migration_under_test', path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            with Session(connection, join_transaction_mode='create_savepoint') as session:
                yield PgVectorChunkRepository(session)
        finally:
            transaction.rollback()
    engine.dispose()


def source():
    return DocumentMetadata(source_id='live-source', file_name='test.pdf', document_title='Test',
        document_types=['REGULATION', 'PROCEDURE'], regulations=[2018, 2023], programs=['CAIE', 'CESS'],
        languages=['en'], official_status='OFFICIAL', file_hash='a' * 64, page_count=2)


def draft(index=1, text_value='Regulation 2023 CAIE academic rule'):
    return MetadataEnricher().enrich(ChunkDraft(chunk_id=f'live:{index}', source_id='live-source',
        text=text_value, page_start=1, page_end=1, section='Registration', chunk_index=index,
        text_hash='b' * 64), source())


def vector(axis=0):
    values = [0.0] * RagChunk.embedding.type.dim
    values[axis] = 1.0
    return values


def stored(index=1, text_value='Regulation 2023 CAIE academic rule', axis=0):
    return StoredChunk(**draft(index, text_value).model_dump(), embedding=vector(axis),
        embedding_model='deterministic-live-test', pipeline_version='test', official_status='OFFICIAL')


def counts(repo):
    return tuple(repo.session.scalar(select(func.count()).select_from(cls)) for cls in (RagSource, RagChunk))


def test_insert_search_and_migration_schema(repo):
    repo.replace_source(source(), [stored(), stored(2, 'Other procedure', 1)])
    assert counts(repo) == (1, 2)
    result = repo.search(vector(), RetrievalFilters(), 1)[0]
    assert result.chunk_id == 'live:1'
    assert result.score == pytest.approx(1.0)
    assert result.model_dump(exclude={'score'}) == dict(chunk_id='live:1', text='Regulation 2023 CAIE academic rule',
        source_id='live-source', file_name='test.pdf', page_start=1, page_end=1, section='Registration',
        document_type='REGULATION', regulation=2023, program='CAIE', language='en', topic='general')
    inspector = inspect(repo.session.connection())
    for cls in (RagSource, RagChunk):
        actual = {c['name']: c for c in inspector.get_columns(cls.__tablename__)}
        assert set(actual) == set(cls.__table__.columns.keys())
        for col in cls.__table__.columns:
            assert actual[col.name]['nullable'] == col.nullable
            dialect = repo.session.bind.dialect
            assert actual[col.name]['type'].compile(dialect=dialect) == col.type.compile(dialect=dialect)
        assert {i['name'] for i in inspector.get_indexes(cls.__tablename__)} == {i.name for i in cls.__table__.indexes}


@pytest.mark.parametrize('year', [2018, 2023])
def test_regulation_filter(repo, year):
    repo.replace_source(source(), [stored(1, 'Regulation 2018 credit load'), stored(2, 'Regulation 2023 credit load')])
    results = repo.search(vector(), RetrievalFilters(regulation=year), 5)
    assert len(results) == 1
    assert results[0].regulation == year


def test_program_filter(repo):
    repo.replace_source(source(), [stored(1, 'CAIE credit load'), stored(2, 'CESS credit load')])
    results = repo.search(vector(), RetrievalFilters(program='CAIE'), 5)
    assert [r.program for r in results] == ['CAIE']


def test_document_type_filter(repo):
    repo.replace_source(source(), [stored(1, 'Academic rule regulation'), stored(2, 'Upload procedure')])
    results = repo.search(vector(), RetrievalFilters(document_types=['REGULATION']), 5)
    assert [r.document_type for r in results] == ['REGULATION']


def pipeline(repo):
    return RagIngestionPipeline(None, None, None, MetadataEnricher(),
        HashTestEmbeddingProvider(RagChunk.embedding.type.dim), repo, 'live-test')


def test_idempotent_reingestion(repo):
    ingest = pipeline(repo)
    assert ingest.ingest_prepared(source(), [draft()]).status == 'INGESTED'
    before = counts(repo)
    assert ingest.ingest_prepared(source(), [draft()]).status == 'SKIPPED_UNCHANGED'
    assert counts(repo) == before == (1, 1)


def test_changed_source_replacement(repo):
    ingest = pipeline(repo)
    ingest.ingest_prepared(source(), [draft()])
    changed = source().model_copy(update={'file_hash': 'c' * 64})
    assert ingest.ingest_prepared(changed, [draft(2, 'Updated CAIE procedure')]).status == 'INGESTED'
    assert counts(repo) == (1, 1)
    assert repo.session.get(RagChunk, 'live:1') is None
    assert repo.get_source_state(changed.source_id).file_hash == 'c' * 64
    result = repo.search(ingest.embedder.embed_query('Updated CAIE procedure'), RetrievalFilters(), 5)
    assert [r.chunk_id for r in result] == ['live:2']
    assert ingest.ingest_prepared(changed, [draft(2, 'Updated CAIE procedure')]).status == 'SKIPPED_UNCHANGED'
