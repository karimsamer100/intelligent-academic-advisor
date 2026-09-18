# RAG Pipeline v0 — Requirements Traceability

| Task requirement | Status | Implementation / evidence |
|---|---|---|
| Official/approved source inputs | DONE | `AcademicDataFoundationAdapter`, source registry reuse |
| Text extraction | DONE | `PyMuPDFExtractor`, `FoundationExtractedTextExtractor` |
| Preserve page mapping | DONE | one-based `PageText.page_number`; page-bounded chunks |
| Extraction failures/empty pages reported | DONE | extractor + `validation/validators.py` + logging |
| Cleaning without rewriting official text | DONE | `AcademicTextCleaner` |
| Configurable chunk size/overlap | DONE | environment settings + `SectionAwarePageChunker` |
| Heading/paragraph/page-aware chunking | DONE | `SectionAwarePageChunker` |
| Do not mix unrelated 18/23 in a chunk | DONE | page-bound chunks + explicit scope enrichment + strict filtering |
| Document metadata contract | DONE | `DocumentMetadata` + `rag_sources` |
| Chunk metadata contract | DONE | `ChunkDraft` / `StoredChunk` + `rag_chunks` |
| Chunk metadata more specific where possible | DONE | `MetadataEnricher` |
| Arabic + English local embeddings | DONE | replaceable `SentenceTransformerEmbeddingProvider`, configurable default |
| Embedding dimension known/validated | DONE | provider property + fail-fast validator + DB dimension setting |
| PostgreSQL + pgvector storage | DONE | ORM + Alembic migration |
| Vector index | DONE | cosine HNSW index in migration |
| Idempotent ingestion | DONE | state check using source hash + pipeline version + model; transactional replacement |
| Retrieval service isolated from API routing | DONE | `DocumentSearchService`, `RAGService` |
| Regulation filter | DONE | applicability array SQL filter |
| Program filter | DONE | applicability array SQL filter |
| Document type filter | DONE | canonical document type filter |
| Language filter | DONE | chunk language filter |
| Official status filter | DONE | chunk/source status filter |
| Top-k semantic retrieval | DONE | pgvector cosine search |
| Citation-ready response | DONE | `RetrievedEvidence` preserves file/page/section/source |
| Basic manual smoke set | DONE | `data/smoke_tests/rag_smoke_tests.json` |
| Unsupported query case | DONE | smoke case + optional calibrated `RAG_MIN_SCORE`; no invented default threshold |
| Duplicate chunk detection | DONE | validation + primary key |
| Missing source/page/regulation validation | DONE | `validation/validators.py` |
| Embedding / DB failures surfaced | DONE | validation + transactional exception propagation/logging |
| Configuration via env | DONE | `core/config.py`, `.env.example` |
| Logging | DONE | JSON logger + ingestion/retrieval event logs |
| No final answer generation | DONE | no LLM synthesis in module |
| No planning/eligibility logic | DONE | deliberately absent |
| README/run instructions | DONE | root `README.md` |
| Initial small dataset | DONE | default 3-source proof set from 2018, 2023, procedure documents |
