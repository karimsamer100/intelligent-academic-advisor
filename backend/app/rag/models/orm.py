"""RAG mappings matching migration 0001_rag_pgvector."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import VECTOR
from app.core.config import get_settings
from app.db.base import Base

dimension = get_settings().embedding_dimension

class RagSource(Base):
    __tablename__ = 'rag_sources'
    source_id = sa.Column('source_id', sa.String(180), primary_key=True)
    file_name = sa.Column('file_name', sa.String(500), nullable=False)
    document_title = sa.Column('document_title', sa.String(500), nullable=False)
    document_types = sa.Column('document_types', postgresql.ARRAY(sa.String(100)), nullable=False, server_default='{}')
    regulations = sa.Column('regulations', postgresql.ARRAY(sa.Integer()), nullable=False, server_default='{}')
    programs = sa.Column('programs', postgresql.ARRAY(sa.String(100)), nullable=False, server_default='{}')
    languages = sa.Column('languages', postgresql.ARRAY(sa.String(20)), nullable=False, server_default='{}')
    effective_year = sa.Column('effective_year', sa.Integer())
    version = sa.Column('version', sa.String(100))
    official_status = sa.Column('official_status', sa.String(120), nullable=False)
    file_hash = sa.Column('file_hash', sa.String(64), nullable=False)
    relative_path = sa.Column('relative_path', sa.String(1000))
    authority_level = sa.Column('authority_level', sa.String(120))
    verification_state = sa.Column('verification_state', sa.String(120))
    page_count = sa.Column('page_count', sa.Integer())
    source_metadata = sa.Column('source_metadata', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"))
    embedding_model = sa.Column('embedding_model', sa.String(300), nullable=False)
    pipeline_version = sa.Column('pipeline_version', sa.String(80), nullable=False)
    expected_chunk_count = sa.Column('expected_chunk_count', sa.Integer(), nullable=False, server_default='0')
    ingested_at = sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())

class RagChunk(Base):
    __tablename__ = 'rag_chunks'
    chunk_id = sa.Column('chunk_id', sa.String(240), primary_key=True)
    source_id = sa.Column('source_id', sa.String(180), sa.ForeignKey('rag_sources.source_id', ondelete='CASCADE'), nullable=False)
    text = sa.Column('text', sa.Text(), nullable=False)
    text_hash = sa.Column('text_hash', sa.String(64), nullable=False)
    embedding = sa.Column('embedding', VECTOR(dimension), nullable=False)
    page_start = sa.Column('page_start', sa.Integer(), nullable=False)
    page_end = sa.Column('page_end', sa.Integer(), nullable=False)
    section = sa.Column('section', sa.String(500))
    document_type = sa.Column('document_type', sa.String(100))
    regulation = sa.Column('regulation', sa.Integer())
    program = sa.Column('program', sa.String(100))
    language = sa.Column('language', sa.String(20))
    topic = sa.Column('topic', sa.String(100))
    chunk_index = sa.Column('chunk_index', sa.Integer(), nullable=False)
    applicable_document_types = sa.Column('applicable_document_types', postgresql.ARRAY(sa.String(100)), nullable=False, server_default='{}')
    applicable_regulations = sa.Column('applicable_regulations', postgresql.ARRAY(sa.Integer()), nullable=False, server_default='{}')
    applicable_programs = sa.Column('applicable_programs', postgresql.ARRAY(sa.String(100)), nullable=False, server_default='{}')
    official_status = sa.Column('official_status', sa.String(120), nullable=False)
    embedding_model = sa.Column('embedding_model', sa.String(300), nullable=False)
    pipeline_version = sa.Column('pipeline_version', sa.String(80), nullable=False)
    chunk_metadata = sa.Column('chunk_metadata', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"))
    ingested_at = sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())

sa.Index("ix_rag_sources_official_status", RagSource.official_status)
for name in ("source_id", "document_type", "regulation", "program", "language", "topic", "official_status"):
    sa.Index(f"ix_rag_chunks_{name}", getattr(RagChunk, name))
for name in ("applicable_document_types", "applicable_regulations", "applicable_programs"):
    sa.Index(f"ix_rag_chunks_{name}", getattr(RagChunk, name), postgresql_using="gin")
sa.Index("ix_rag_chunks_embedding_hnsw", RagChunk.embedding, postgresql_using="hnsw",
         postgresql_ops={"embedding": "vector_cosine_ops"},
         postgresql_with={"m": 16, "ef_construction": 64})
