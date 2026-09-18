# RAG Pipeline v0 — Implementation Report

## Delivered

- replaceable PDF extractor
- Academic Data Foundation extracted-text adapter
- conservative cleaner
- page/section-aware chunker
- chunk metadata enrichment
- local multilingual embedding provider
- SQLAlchemy pgvector persistence
- Alembic migration including pgvector extension and HNSW index
- idempotent source ingestion
- strict regulation/program/document-type/language/status filters
- citation-ready evidence contract
- backend `RAGService` boundary
- manual smoke-test dataset and runner
- unit and integration tests
- environment configuration
- Docker pgvector service
- run/integration/design documentation

## Explicitly outside scope

No final answer generation, LLM/orchestrator behavior, academic eligibility computation, prerequisite execution, semester planning, track recommendation, advisor escalation, frontend, voice, or conversion of unverified text into executable rules was added.

## Upstream package handling

The Academic Data Foundation's source registry and page-level extracted text are treated as upstream inputs. Existing legacy chunks are not blindly loaded because RAG v0 needs richer chunk-level metadata and stricter scope semantics.

## Academic authority note

The upstream package labels collected institutional sources and still contains academic-review/authority-precedence states that may be pending. This implementation preserves those fields; it does not upgrade a source to `OFFICIAL` or resolve academic conflicts on its own.
