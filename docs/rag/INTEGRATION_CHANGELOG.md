# RAG v0 Integration Changelog

The uploaded project was a backend repository skeleton. This integration preserves that structure and fills the agreed Backend Foundation + RAG v0 boundaries.

## Added backend runtime

- `backend/app/main.py`
- `backend/app/api/router.py`
- `backend/app/api/dependencies.py`
- `backend/app/api/routes/health.py`
- `backend/app/api/routes/rag.py`
- `backend/app/core/config.py`
- `backend/app/core/logging.py`
- `backend/app/core/exceptions.py`
- `backend/app/db/*`
- `backend/Dockerfile`
- `backend/requirements.txt`
- `backend/pyproject.toml`

## Integrated RAG v0

- extraction, cleaning and section-aware chunking
- metadata enrichment and applicability scope
- local sentence-transformers embeddings
- SQLAlchemy pgvector persistence
- strict filtered retrieval
- idempotent ingestion
- Academic Data Foundation adapter
- prepared-sample adapter
- evidence-only `RAGService`
- API request/response contract

## Database

- Alembic configured
- migration enables pgvector
- `rag_sources` and `rag_chunks`
- metadata indexes
- GIN applicability indexes
- cosine HNSW vector index

## Developer experience

- root Docker Compose stack
- `.env.example`
- included three-source proof set
- full-foundation unpack helper
- smoke-test runner
- README and quick test guide
