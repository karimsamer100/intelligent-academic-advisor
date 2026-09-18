# Local Intelligent Academic Advisor

This repository is the integrated backend foundation + **RAG Pipeline v0** for the Local Intelligent Academic Advisor project.

The current runnable slice does one thing deliberately well: it retrieves official academic evidence with strict academic scope and citation-ready metadata. It **does not** generate final student answers or perform academic planning.

## What is implemented

```text
Official PDF / Academic Data Foundation
  -> page-preserving extraction
  -> conservative cleaning
  -> section/page-aware chunking
  -> academic metadata enrichment
  -> local multilingual embeddings
  -> PostgreSQL + pgvector
  -> strict metadata-filtered semantic search
  -> evidence + source/page citations
  -> FastAPI endpoint
```

Included backend foundation:

- FastAPI application and versioned API
- PostgreSQL + pgvector
- SQLAlchemy 2.x
- Alembic migration
- Docker Compose local environment
- centralized typed configuration
- structured logging and consistent errors
- health/readiness endpoints
- RAG service boundary
- unit/API/integration tests

Included RAG v0:

- replaceable PDF extraction interfaces
- Academic Data Foundation adapter
- conservative cleaner
- page/section-aware chunker
- chunk-specific regulation/program/document-type/language/topic metadata
- local `sentence-transformers` embedding provider (default `BAAI/bge-m3`)
- idempotent ingestion
- pgvector cosine retrieval + HNSW index
- strict Regulation 2018/2023 filtering
- citation-ready retrieval response
- prepared 3-source proof dataset
- manual retrieval smoke tests

## 1. Fastest way to run it (Docker Desktop)

### Step 1 — create `.env`

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

The defaults are sufficient for the included proof set.

### Step 2 — start PostgreSQL + backend

```bash
docker compose up -d --build
```

The backend container automatically runs:

```text
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Verify:

- API health: `http://localhost:8000/health`
- versioned health: `http://localhost:8000/api/v1/health`
- DB/pgvector readiness: `http://localhost:8000/api/v1/ready`
- Swagger UI: `http://localhost:8000/docs`

Expected readiness response resembles:

```json
{
  "status": "ready",
  "database": "ok",
  "pgvector": "ok",
  "pgvector_version": "0.8.6"
}
```

## 2. Ingest the included proof dataset

The repository ships with three prepared official-source samples (2018 regulation, 2023 regulation, and student guideline) so you can test without installing the full Academic Data Foundation first.

Run:

```bash
docker compose exec backend python -m app.rag.ingestion.cli ingest-prepared --prepared-dir /app/data/prepared_sample
```

On first production embedding use, `sentence-transformers` downloads the configured local model (`BAAI/bge-m3`) into the persistent Docker Hugging Face cache. No cloud LLM/API is used for retrieval.

A successful first ingestion reports `INGESTED`. Running the same command again should report `SKIPPED_UNCHANGED` for unchanged sources.

## 3. Test retrieval through the API

### Swagger

Open:

```text
http://localhost:8000/docs
```

Use `POST /api/v1/rag/search` with:

```json
{
  "query": "How many credits can a student with a GPA of at least 3 register in a main semester?",
  "regulation": 23,
  "program": null,
  "document_types": ["REGULATION"],
  "language": "en",
  "top_k": 5
}
```

`23` is normalized to canonical `2023`; `18` is normalized to `2018`.

The response is evidence only:

```json
{
  "results": [
    {
      "chunk_id": "...",
      "text": "...",
      "score": 0.88,
      "source_id": "...",
      "file_name": "...pdf",
      "page_start": 8,
      "page_end": 8,
      "section": "...",
      "document_type": "REGULATION",
      "regulation": 2023,
      "program": "UEL",
      "language": "en",
      "topic": "credit_load"
    }
  ]
}
```

### PowerShell example

```powershell
$body = @{
  query = "How many credits can a student with a GPA of at least 3 register in a main semester?"
  regulation = 23
  document_types = @("REGULATION")
  language = "en"
  top_k = 5
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/rag/search" `
  -ContentType "application/json" `
  -Body $body
```

## 4. Test retrieval from the CLI

```bash
docker compose exec backend python -m app.rag.ingestion.cli search "What is the maximum program duration?" --regulation 2023 --document-type REGULATION --language en --top-k 5
```

## 5. Run the automated tests

Unit/API tests (no live DB required by the tests themselves):

```bash
docker compose exec backend pytest -q -m "not integration"
```

Live pgvector infrastructure test:

```bash
docker compose exec -e RUN_PGVECTOR_TESTS=1 backend pytest -q -m integration
```

Manual semantic retrieval smoke set after ingestion:

```bash
docker compose exec backend python /app/scripts/run_rag_smoke_tests.py
```

The smoke set covers exact lookup, paraphrased lookup, Regulation 2018, Regulation 2023, similar wording across both regulations, a procedure query, and an unsupported query.

## 6. Ingest the full Academic Data Foundation

The full Academic Data Foundation is intentionally not duplicated inside this repository.

Put it at:

```text
data/academic_foundation/
```

The directory must contain:

```text
data/academic_foundation/rag/source_registry.json
```

You can install the ZIP automatically from the repository root:

```bash
python scripts/unpack_academic_foundation.py /path/to/Academic_Data_Foundation_SUBMISSION_READY.zip
```

Then ingest the default three-source verification slice:

```bash
docker compose exec backend python -m app.rag.ingestion.cli ingest-foundation --foundation-path /app/data/academic_foundation
```

After checking retrieval quality, ingest every source marked `rag_ingest_recommended`:

```bash
docker compose exec backend python -m app.rag.ingestion.cli ingest-foundation --foundation-path /app/data/academic_foundation \
  --all-rag-sources
```

To bypass the Academic Data Foundation extracted-page JSON and re-extract from the original PDFs using PyMuPDF:

```bash
docker compose exec backend python -m app.rag.ingestion.cli ingest-foundation --foundation-path /app/data/academic_foundation \
  --fresh-extraction
```

## 7. Inspect chunks without embeddings/database

```bash
docker compose exec backend python -m app.rag.ingestion.cli prepare-foundation --foundation-path /app/data/academic_foundation --output-dir /app/data/prepared_rag
```

Use `--all-rag-sources` to prepare all recommended sources.

## 8. Important filtering behavior

Trusted context is restrictive. For example:

```json
{"regulation": 23}
```

is treated as Regulation 2023 and prevents a Regulation-2018-only chunk from being returned merely because it is semantically similar.

Program filtering is equally strict. Do not supply a program filter unless the trusted student/program context is known and represented in approved source metadata.

## 9. Configuration

Main variables are in `.env.example`:

```text
DATABASE_URL
ACADEMIC_DATA_FOUNDATION_PATH
DOCUMENTS_PATH
EMBEDDING_MODEL
EMBEDDING_DEVICE
EMBEDDING_DIMENSION
EMBEDDING_BATCH_SIZE
CHUNK_SIZE
CHUNK_OVERLAP
CHUNK_MIN_CHARS
RAG_TOP_K
RAG_MAX_TOP_K
RAG_MIN_SCORE
PIPELINE_VERSION
```

If you replace the embedding model with a model that uses a different vector dimension, set `EMBEDDING_DIMENSION` **before creating the database schema**. A database already migrated with one vector dimension must be recreated/migrated before using a different dimension.

## 10. Project structure

```text
backend/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── router.py
│   │   └── routes/
│   │       ├── health.py
│   │       └── rag.py
│   ├── core/
│   ├── db/
│   ├── rag/
│   │   ├── extractors/
│   │   ├── cleaners/
│   │   ├── chunkers/
│   │   ├── metadata/
│   │   ├── embeddings/
│   │   ├── ingestion/
│   │   ├── repositories/
│   │   ├── retrieval/
│   │   ├── models/
│   │   └── validation/
│   ├── schemas/
│   └── services/
├── alembic/
├── tests/
├── Dockerfile
└── requirements.txt

data/
├── prepared_sample/
└── smoke_tests/
```

## 11. Current scope boundary

RAG v0 returns official evidence. It does **not** implement:

- final LLM answer generation
- eligibility/prerequisite computation
- semester planning
- track recommendation
- advisor escalation
- frontend

Those belong to later components of the Local Intelligent Academic Advisor architecture.

## 12. Further implementation documentation

See:

- `docs/rag/REQUIREMENTS_TRACEABILITY.md`
- `docs/rag/DESIGN_NOTES.md`
- `docs/rag/ACADEMIC_DATA_FOUNDATION_INTEGRATION.md`
- `docs/rag/RAG_TASK_IMPLEMENTATION_REPORT.md`
- `reports/INTEGRATION_VALIDATION.md`
