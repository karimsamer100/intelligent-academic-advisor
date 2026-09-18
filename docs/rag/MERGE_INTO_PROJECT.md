# Merge Into the Main Project

This package is designed to merge into the agreed backend foundation rather than replace it.

## Copy/merge these directories

```text
backend/app/rag/                 -> backend/app/rag/
backend/app/services/rag_service.py -> backend/app/services/rag_service.py
backend/app/schemas/rag.py       -> merge with existing shared RAG schemas if already present
backend/alembic/versions/0001_rag_pgvector.py -> add as the next migration, renaming revision/down_revision as needed
backend/tests/unit/*             -> backend/tests/
data/smoke_tests/*               -> data/smoke_tests/
scripts/run_rag_smoke_tests.py   -> scripts/
```

## Do not overwrite blindly

If the Backend Foundation task has already created:

- `core/config.py`
- `db/session.py`
- `db/base.py`
- `alembic/env.py`
- `.env.example`
- `requirements.txt`

merge the RAG-specific settings/dependencies rather than replacing the teammate's files.

## Required RAG settings to add to the shared backend config

```text
ACADEMIC_DATA_FOUNDATION_PATH
EMBEDDING_MODEL
EMBEDDING_DEVICE
EMBEDDING_DIMENSION
EMBEDDING_BATCH_SIZE
EMBEDDING_CACHE_DIR (optional)
CHUNK_SIZE
CHUNK_OVERLAP
CHUNK_MIN_CHARS
RAG_TOP_K
RAG_MAX_TOP_K
RAG_MIN_SCORE (optional)
PIPELINE_VERSION
PRESERVE_RAW_EXTRACTION
RAW_EXTRACT_DIR
```

## Migration integration

If the backend already has an Alembic baseline, do not keep `down_revision = None`. Generate a new project migration or edit the included migration's `down_revision` to point to the current backend head.

The migration must retain:

- `CREATE EXTENSION IF NOT EXISTS vector`
- `rag_sources`
- `rag_chunks`
- metadata indexes
- applicability GIN indexes
- HNSW cosine index

## Service integration

The intended call chain is:

```text
FastAPI route
  -> RAGService
      -> DocumentSearchService
          -> EmbeddingProvider
          -> ChunkRepository (pgvector)
```

No FastAPI route is required inside the RAG module itself. This keeps retrieval logic isolated from routing and lets the backend foundation own API composition.
