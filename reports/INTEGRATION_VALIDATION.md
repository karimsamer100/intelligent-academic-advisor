# Integrated RAG validation

The current validation is recorded in [TEST_REPORT.md](TEST_REPORT.md), including exact commands and limitations. This supersedes the previous environment-limited report.

- Compile/import: PASS.
- Non-integration tests: 29 passed, 7 deselected.
- Real migration + PostgreSQL/pgvector repository tests: 7 passed, 29 deselected.
- Production BGE-M3 CPU embeddings: PASS, 1024 dimensions; mismatch rejected.
- Three-source real proof ingestion: 80 chunks.
- Real-stack smoke: 5 passed, 0 failed, 1 unsupported-query calibration pending.
- Full preparation: 11 sources, 3803 unique chunks, no empty chunks or invalid page metadata.
- Fresh extraction: 55 pages, 82 chunks, one explicitly empty page; raw/debug verified.

Machine-readable evidence: [REAL_DATA_VALIDATION.json](REAL_DATA_VALIDATION.json), [PRODUCTION_EMBEDDING.json](PRODUCTION_EMBEDDING.json), [RAG_SMOKE_RESULTS.json](RAG_SMOKE_RESULTS.json).

RAG remains evidence-only. No Planning Engine, LLM generation, Decision Layer, authentication, or global DB redesign was added.
