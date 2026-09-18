# Academic Data Foundation Integration

## What the upstream package already provides

The supplied Academic Data Foundation package contains:

- original institutional PDFs
- `rag/source_registry.json`
- page-preserving `raw/extracted_text/*.json`
- a legacy `rag/chunks.jsonl`
- source SHA-256 hashes
- project role / priority / authority metadata

Its RAG build report records **11 recommended RAG sources and 3,712 legacy chunks**.

## What this RAG implementation reuses

By default the RAG v0 ingestion path reuses:

1. source identity and authority metadata from `rag/source_registry.json`
2. source file hashes
3. page-preserving extracted text from `raw/extracted_text/<source_id>.json`
4. original PDFs as fallback / verification inputs

The existing `rag/chunks.jsonl` is not used as the final vector-ingestion format because its chunks do not contain all RAG v0 fields and use a simpler character-based splitter. This implementation rebuilds chunks from page-level extracted text while preserving source provenance.

## Why this avoids duplicated work

Text extraction is the expensive/noisy part of PDF processing. Reusing the Academic Data Foundation page extraction avoids repeating it for the first integration while still allowing `--fresh-extraction` to validate or replace that extraction later.

## Upstream metadata gaps are not silently invented

Examples:

- Some 2023 general-regulation sources have no explicit `programs[]` scope.
- Multi-bylaw sources may be tagged `[2018, 2023]` at document level even when individual chunks are ambiguous.

RAG v0 handles these conservatively:

- precise chunk scope is filled only when supported by source metadata or clear text markers
- explicit source-level applicability is retained in `applicable_regulations[]` / `applicable_programs[]`
- an unscoped program is not treated as universally applicable under a trusted program filter

If academic reviewers approve broader applicability, update the upstream registry or an approved metadata layer and re-ingest.
