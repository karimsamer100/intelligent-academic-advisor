# Integrated Project Validation

Validation performed after merging RAG Pipeline v0 into the uploaded `intelligent-academic-advisor-main` project skeleton.

## Automated checks

- Python application compile: **PASS**
- Non-integration pytest suite: **17 passed, 1 integration test deselected**
- FastAPI root health contract: **PASS**
- FastAPI versioned health contract: **PASS**
- Readiness response contract: **PASS** (DB call mocked in unit/API suite)
- RAG API service-boundary test: **PASS**
- Regulation short-form normalization (`18/23` -> `2018/2023`): **PASS**
- Prepared-sample adapter: **PASS**

## Prepared-sample pipeline check

The included three-source sample was loaded through the integrated prepared-ingestion path using the deterministic local test embedder and in-memory repository:

- `SRC-CESS_NEW_BYLAW_2018_PDF`: 27 chunks inserted
- `SRC-BYLAW_2023_GENERAL_RULES_REGULATIONS_UEL_PDF`: 31 chunks inserted
- `SRC-STUDENT_S_GUIDLINE_BOOKLET_V1_5_PDF`: 22 chunks inserted
- total: 80 chunks

Checks:

- second unchanged ingestion -> `SKIPPED_UNCHANGED`: **PASS**
- Regulation 2023 filtered retrieval returned no 2018-only source: **PASS**

## Environment limitation of this validation runtime

The current execution environment does not provide Docker, so the Docker/PostgreSQL/pgvector services could not be started here. The repository includes the Docker Compose stack, Alembic migration, pgvector integration test, and production sentence-transformers provider for execution on the developer machine.

## Full Academic Data Foundation preparation regression

Using the final integrated project code against the actual Academic Data Foundation package:

- RAG-recommended sources: **11**
- prepared chunks: **3,803**
- unique chunk IDs: **3,803**
- empty chunks: **0**
- missing/invalid page metadata: **0**
- result: **PASS**

## Fresh PDF extraction regression

The default three-source slice was also reprocessed directly from original PDFs with PyMuPDF:

- PDF pages processed: **55**
- chunks produced: **82**
- extraction result: **PASS**
- one genuinely empty PDF page was explicitly reported as a warning rather than silently treated as extracted text
