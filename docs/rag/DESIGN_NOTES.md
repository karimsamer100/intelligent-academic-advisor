# RAG v0 Design Notes

## 1. Evidence retrieval, not answer generation

The retrieval service returns `RetrievedEvidence` objects. There is no prompt construction, answer synthesis, or academic decision logic in this package.

## 2. Provenance model

Page provenance is mandatory. Chunks are intentionally prevented from crossing PDF page boundaries in v0, which keeps citations simple and auditable. `page_start` and `page_end` are still both stored so the response contract remains future-compatible with multi-page chunks.

## 3. Text preservation

Cleaning is conservative. Repeated headers/footers are removed only at page edges after repetition is observed across a significant fraction of pages. Numeric values are not parsed/reformatted, official text is not summarized, and translations are not substituted for originals.

The original extracted page text can be persisted to `RAW_EXTRACT_DIR` for debugging.

## 4. Scope filtering

`regulation` and `program` represent the most precise single chunk scope that can be supported. Arrays represent explicit applicability inherited from the source. Retrieval filters the arrays, not semantic content, when trusted context exists.

This prevents semantically similar Regulation 18 text from contaminating a Regulation 23 request.

## 5. Vector search

The production repository uses cosine distance in pgvector. HNSW is used for the first approximate index because it does not require a training step and is appropriate for an incrementally ingested v0 corpus. Exact correctness can still be checked by temporarily disabling index scans during evaluation if needed.

## 6. Unsupported questions

Vector search normally returns a nearest neighbor even for unrelated questions. Therefore unsupported-query handling needs a calibrated score/relevance threshold or a later reranker/classifier. RAG v0 supports an optional `RAG_MIN_SCORE`, but the default is unset to avoid inventing a threshold before measurement.

## 7. Embedding model

The default is a local multilingual model (`BAAI/bge-m3`) suitable for Arabic/English retrieval. The provider interface is replaceable. Model name, device, cache path, batch size and vector dimension are environment settings.

Changing to a model with a different dimension requires a matching database migration; the code fails fast on dimension mismatch.
