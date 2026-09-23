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

## Applicability correction and deployment

The ingestion pipeline appends `:scope-v2` to the configured pipeline version.
Re-ingest every deployed source after merging: unchanged-file checks must not retain
pre-fix applicability arrays. Prepared exports are re-enriched before validation.
Existing embeddings and source text are not academic rules.

The local RAG `.gitignore` explicitly includes the `models` and `embeddings` Python
packages because the root ignore rules otherwise hide them as generated artifacts.
Keep these source packages tracked when merging.

Run `RUN_PGVECTOR_TESTS=1 python -m pytest -q -m integration` with a PostgreSQL URL
(optionally `PGVECTOR_TEST_DATABASE_URL`). Tests apply the real migration in unique,
transactional schemas and roll them back. The test role needs schema creation rights.
The migration's vector dimension and `EMBEDDING_DIMENSION` must agree; changing the
model dimension requires an explicit RAG schema migration and re-ingestion.

`scripts/run_rag_smoke_tests.py --prepared-dir data/prepared_sample --output reports/RAG_SMOKE_RESULTS.json`
uses the real provider and PostgreSQL with a fresh rollback-only proof schema.
Exit 2 means unsupported-query threshold calibration is pending; it is not an all-pass result.
The default mode still searches the existing database.

Threshold calibration remains pending. The six-case proof is insufficient to choose
a deployment-wide cutoff. Keep `RAG_MIN_SCORE` configurable; an empty result remains
evidence absence for the future Decision Layer to interpret.

After refreshing the full corpus, audit the persisted data and real API dependencies:

```text
python -m app.rag.validation.verify_runtime --foundation-path /app/data/academic_foundation --smoke-cases /app/data/smoke_tests/rag_smoke_tests.json --output /app/reports/RUNTIME_VERIFICATION.json
```

This compares every expected chunk with PostgreSQL, validates vectors and ingestion
versions, checks unchanged re-ingestion without count growth, and exercises API
readiness and citation lookup without dependency overrides. It also measures an
English diagnostic set of supported queries, unrelated queries, and requests for
student-specific/live facts. Generated diagnostic examples are not held-out,
independently labeled calibration data; inspect the score overlap and threshold
sweep before drawing conclusions. `PASS_WITH_CALIBRATION_PENDING` confirms the
runtime contracts, not reliable rejection of all unsupported questions.
