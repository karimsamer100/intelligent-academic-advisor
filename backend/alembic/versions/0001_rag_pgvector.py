"""Create RAG source/chunk tables with pgvector HNSW index."""
from __future__ import annotations

import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import VECTOR

revision = "0001_rag_pgvector"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    dimension = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "rag_sources",
        sa.Column("source_id", sa.String(180), primary_key=True),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("document_title", sa.String(500), nullable=False),
        sa.Column("document_types", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("regulations", postgresql.ARRAY(sa.Integer()), nullable=False, server_default="{}"),
        sa.Column("programs", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("languages", postgresql.ARRAY(sa.String(20)), nullable=False, server_default="{}"),
        sa.Column("effective_year", sa.Integer()),
        sa.Column("version", sa.String(100)),
        sa.Column("official_status", sa.String(120), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("relative_path", sa.String(1000)),
        sa.Column("authority_level", sa.String(120)),
        sa.Column("verification_state", sa.String(120)),
        sa.Column("page_count", sa.Integer()),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("embedding_model", sa.String(300), nullable=False),
        sa.Column("pipeline_version", sa.String(80), nullable=False),
        sa.Column("expected_chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rag_sources_official_status", "rag_sources", ["official_status"])

    op.create_table(
        "rag_chunks",
        sa.Column("chunk_id", sa.String(240), primary_key=True),
        sa.Column("source_id", sa.String(180), sa.ForeignKey("rag_sources.source_id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("embedding", VECTOR(dimension), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(500)),
        sa.Column("document_type", sa.String(100)),
        sa.Column("regulation", sa.Integer()),
        sa.Column("program", sa.String(100)),
        sa.Column("language", sa.String(20)),
        sa.Column("topic", sa.String(100)),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("applicable_document_types", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("applicable_regulations", postgresql.ARRAY(sa.Integer()), nullable=False, server_default="{}"),
        sa.Column("applicable_programs", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("official_status", sa.String(120), nullable=False),
        sa.Column("embedding_model", sa.String(300), nullable=False),
        sa.Column("pipeline_version", sa.String(80), nullable=False),
        sa.Column("chunk_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for col in ("source_id", "document_type", "regulation", "program", "language", "topic", "official_status"):
        op.create_index(f"ix_rag_chunks_{col}", "rag_chunks", [col])
    op.create_index("ix_rag_chunks_applicable_document_types", "rag_chunks", ["applicable_document_types"], postgresql_using="gin")
    op.create_index("ix_rag_chunks_applicable_regulations", "rag_chunks", ["applicable_regulations"], postgresql_using="gin")
    op.create_index("ix_rag_chunks_applicable_programs", "rag_chunks", ["applicable_programs"], postgresql_using="gin")
    op.execute(
        "CREATE INDEX ix_rag_chunks_embedding_hnsw ON rag_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.drop_table("rag_chunks")
    op.drop_table("rag_sources")
