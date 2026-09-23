# Final RAG validation — 2026-09-23

This report replaces historical validation claims. Results below were executed on the fixed working tree based on `bbb1ef9`, branch `KHM`.

| Check | Actual result |
|---|---|
| Application compileall | PASS, exit 0 |
| Non-integration pytest | 29 passed, 7 deselected; includes RAG API contract |
| Live PostgreSQL/pgvector pytest | 7 passed, 29 deselected |
| Production BGE-M3 on CPU | PASS: query 1024 dimensions; 2 documents, each 1024 dimensions |
| Wrong configured dimension | PASS: actual 1024 / expected 1025 raises ValueError |
| Prepared proof ingestion | PASS: 3 sources, 27 + 31 + 22 = 80 chunks |
| Isolated real-stack smoke | 5 passed, 0 failed, 1 calibration pending |
| Full foundation preparation | PASS: 11 sources, 3803 unique chunks |
| Fresh original PDF extraction | PASS: 3 PDFs, 55 pages, 82 chunks; page 32 of UEL rules explicitly empty |

Live repository tests apply the existing migration in unique transaction-scoped schemas and exercise insert/search, both regulation directions, program filtering, document-type filtering, idempotency, and changed-source replacement. Schema columns, nullability, PostgreSQL types and index names are compared with the ORM. All test schemas are rolled back.

Full-corpus assertions check page bounds, nonempty chunks, IDs, supported scope, singleton narrowing, and exact inherited applicability for ambiguous chunks. Multi-regulation sources: 40 chunks narrowed, 351 shared. Multi-program sources: 4 narrowed, 122 shared. No unexpected applicability expansion. Fresh extraction checks every page number against each original PDF and reads the raw/debug JSON back.

## Exact executed commands

From repository root, environment setup and existing migration:

```powershell
python -m pip --python .venv/Scripts/python.exe install -r backend/requirements.txt
docker compose up -d postgres
docker compose ps
docker compose run --rm --no-deps -v 'C:/Users/Kareem/intelligent-academic-advisor/backend:/app/backend' backend alembic upgrade head
```

From `backend` (local Python 3.13 virtual environment):

```powershell
..\.venv\Scripts\python -m compileall -q app
..\.venv\Scripts\python -m pytest -q -m 'not integration'
```

From repository root (existing backend image, Python 3.11, final source mounted):

```powershell
docker compose run --rm --no-deps -e RUN_PGVECTOR_TESTS=1 -v 'C:/Users/Kareem/intelligent-academic-advisor/backend:/app/backend' backend python -m pytest -q -m integration

docker compose run --rm --no-deps -v 'C:/Users/Kareem/intelligent-academic-advisor/backend:/app/backend' -v 'C:/Users/Kareem/intelligent-academic-advisor/reports:/app/reports' backend python -m app.rag.validation.verify_embedding --output /app/reports/PRODUCTION_EMBEDDING.json

docker compose run --rm --no-deps -v 'C:/Users/Kareem/intelligent-academic-advisor/backend:/app/backend' backend python -m app.rag.ingestion.cli ingest-prepared --prepared-dir /app/data/prepared_sample

docker compose run --rm --no-deps -e HF_HUB_OFFLINE=1 -v 'C:/Users/Kareem/intelligent-academic-advisor/backend:/app/backend' -v 'C:/Users/Kareem/intelligent-academic-advisor/scripts:/app/scripts' -v 'C:/Users/Kareem/intelligent-academic-advisor/reports:/app/reports' backend python /app/scripts/run_rag_smoke_tests.py --prepared-dir /app/data/prepared_sample --output /app/reports/RAG_SMOKE_RESULTS.json

docker compose run --rm --no-deps -v 'C:/Users/Kareem/intelligent-academic-advisor/backend:/app/backend' -v 'C:/Users/Kareem/intelligent-academic-advisor/reports:/app/reports' -v 'D:/Kareem/downloads/intelligent-academic-advisor-RAG-integrated-final/intelligent-academic-advisor/data/academic_foundation:/app/data/academic_foundation:ro' backend python -m app.rag.validation.verify_real_data --foundation-path /app/data/academic_foundation --prepared-dir /app/data/prepared_sample --output /app/reports/REAL_DATA_VALIDATION.json

git diff --check
git status --short
```

Smoke returns script exit 2 (Compose reports nonzero) for the pending unsupported-query check. It does not claim all-pass. Normal unit runs deselect seven opt-in integration cases. No required test was skipped for missing dependencies or unavailable data in the final run.

## Retrieval quality

Final smoke is restricted to a freshly migrated, rollback-only proof schema populated with real BGE-M3 embeddings. It does not depend on older rows in the developer database.

| Query | Best score |
|---|---:|
| Exact credit-load policy | 0.768950 |
| Credit-load paraphrase | 0.761260 |
| 2018 study duration | 0.625323 |
| 2023 study duration | 0.606752 |
| Procedure | 0.608693 |
| Unsupported cafeteria query | 0.372080 |

The 2018 distractor for the 2023 duration query scores 0.593759 without trusted filtering; the 2023 filter excludes it. Scores alone are not a substitute for metadata filtering.

Threshold calibration is still pending. One negative example is insufficient to recommend a general `RAG_MIN_SCORE`. It remains unset/configurable. With an explicit threshold and no surviving evidence, retrieval returns `[]`; no fallback academic answer is generated.

An earlier smoke against the existing larger database also found all five citations, but its unsupported maximum was 0.4729. This corpus-dependent change reinforces the need for broader calibration. The retained JSON report is the isolated final proof, with complete evidence and scores.

## Environment and limitations

The full source package was located through the original Docker bind mount on D: and accessed read-only. No original source text was changed. Local model caches, raw debug extraction, Python caches, and the virtual environment are excluded from Git.

Existing non-proof database sources must be re-ingested on deployment to replace pre-fix applicability; the `:scope-v2` ingestion version forces replacement. Only the three proof sources were refreshed in the persistent developer database. Full-source preparation was rerun, but full-source embedding/re-ingestion was not part of the proof ingestion request.

Future global Alembic reconciliation remains with Backend/DB integration. Academic authority conflicts remain upstream. The observed deprecation warnings concern the installed FastAPI/httpx/anyio and embedding/PDF library APIs; they did not cause test failures.
