# Final RAG validation — 2026-09-23

Latest verification was executed against commit `351d882` (`fixed rag`), branch `KHM`, plus the new runtime audit tool. Original fix validation was based on `bbb1ef9`. Exact new commands and outcomes are recorded in `VERIFICATION_RUN.json`.


## Complete runtime rerun ? 2026-09-24

The existing backend image was rebuilt from this checkout with `docker compose build backend`, then started using `docker compose up -d backend`. Both backend and PostgreSQL are healthy. The backend remains available at http://localhost:8000/docs.

| Additional check | Actual result |
|---|---|
| Rebuilt-image compileall | PASS |
| Rebuilt-image unit/API tests | 29 passed, 7 deselected |
| Rebuilt-image live integration | 7 passed, 29 deselected |
| Full corpus refresh | 8 sources re-ingested, 3 current sources skipped |
| Persisted corpus versus fresh preparation | All 3803 chunks match, including text, pages, metadata and scope |
| Persisted vectors | All finite, nonzero, 1024 dimensions, expected model and pipeline version |
| Second full ingestion | 11 skipped unchanged; counts remain 11 sources / 3803 chunks |
| API with real dependencies | 7 checks passed, no dependency overrides |
| Actual localhost HTTP | Health, readiness, 5 citation cases and blank-query rejection passed; unsupported case pending |
| Full-corpus smoke, default threshold unset | 5 passed, 0 failed, 1 pending |
| Temporary measured cutoff 0.55 | 6 smoke cases passed, cafeteria query returned [] |
| Broader diagnostic retrieval | All 10 expected citations found; 14 unsupported diagnostic queries scored |

The isolated three-source proof, production-model shape/mismatch verification, full preparation and fresh extraction were also rerun successfully. Their original expected counts in the tables below remain valid.

### Score separation: remaining limitation

The minimum expected-citation score across ten supported queries was **0.567647**. The maximum score on fourteen unsupported queries was **0.599003** (a request for the student's current GPA retrieved generic GPA policy text). These overlap.

- At 0.55, all ten expected citations survive, but two unsupported questions still retrieve evidence.
- At 0.60, all fourteen unsupported questions are rejected, but one expected citation is lost.
- No threshold can retain every expected citation and reject every unsupported query in this diagnostic set.

The 0.55 smoke run is a temporary mechanism test selected from measured scores, not a production recommendation. No environment/default threshold was changed. RAG still returns evidence only and does not fabricate a personal GPA or a fallback academic answer. Generated English diagnostics are not independently reviewed or held-out evaluation data. Production threshold calibration and broader answerability evaluation remain pending.

### Current evidence

- `VERIFICATION_RUN.json`: exact executed commands and actual results.
- `RUNTIME_VERIFICATION.json`: per-source persisted audit, unchanged re-ingestion, 24-query scores, threshold sweep and real-dependency API checks.
- `HTTP_VERIFICATION.json`: actual localhost HTTP responses and citations.
- `RAG_FULL_CORPUS_SMOKE.json`: default full-corpus smoke.
- `RAG_THRESHOLD_PROBE.json`: temporary 0.55 cutoff smoke.
- `RAG_SMOKE_RESULTS.json`: isolated three-source proof.
- `PRODUCTION_EMBEDDING.json` and `REAL_DATA_VALIDATION.json`: rerun model/data verification.

The audit can be repeated using the command documented in `docs/rag/MERGE_INTO_PROJECT.md`. Verification adds no planning, LLM generation, or decision behavior.


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

## Isolated proof retrieval quality

The isolated proof smoke is restricted to a freshly migrated, rollback-only proof schema populated with real BGE-M3 embeddings. It does not depend on older rows in the developer database.

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

The full persistent corpus has now been refreshed: eight older sources were re-ingested (3723 chunks), and three current proof sources were skipped (80 chunks). All 11 sources / 3803 chunks use `rag-v0.1.0:scope-v2`. A second full ingestion skipped all 11 sources and preserved counts exactly. On another deployment, re-ingest any pre-fix sources in the same way.

Future global Alembic reconciliation remains with Backend/DB integration. Academic authority conflicts remain upstream. The observed deprecation warnings concern the installed FastAPI/httpx/anyio and embedding/PDF library APIs; they did not cause test failures.
