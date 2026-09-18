# Test Report

## Automated unit tests

Command:

```bash
cd backend
pytest -q -m "not integration"
```

Result:

```text
10 passed, 1 deselected
```

Covered behavior includes:

- conservative header/footer cleanup with numeric preservation
- page-bound chunking, including preservation of short trailing text
- metadata narrowing for multi-regulation sources
- Arabic/English/mixed language detection
- trusted Regulation 23 filter excluding Regulation 18-only evidence
- idempotent unchanged-source ingestion
- request/response contract validation

## Python compilation

All application and script modules compile successfully with `python -m compileall`.

## Real Academic Data Foundation proof set

The preparation pipeline was executed against three real upstream sources. See `REAL_DATA_VALIDATION.json` and `data/prepared_sample/`.

## Fresh PDF extractor verification

The three real source PDFs were also processed directly with PyMuPDF. All 55 pages were traversed; one empty page (2023 UEL rules PDF page 32) was explicitly reported. The pipeline did not silently drop it.

## Not executable in this sandbox

A live PostgreSQL + pgvector integration test and the production sentence-transformer embedding model could not be executed in this environment because Docker is unavailable and the runtime cannot download missing Python/model dependencies. The optional integration test, migration, Docker Compose service, and production provider are included for execution in the project environment.
