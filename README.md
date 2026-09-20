# Local Intelligent Academic Advisor - Backend Foundation

FastAPI + PostgreSQL (pgvector) + SQLAlchemy 2.x + Alembic, runnable with Docker Compose.
The backend includes the deterministic, framework-independent Planning Engine and exposes it to backend application code through a thin `PlanningService` adapter. Concrete RAG retrieval, HTTP planning routes, LLM orchestration, and the frontend remain separate integration work.

## Quick start (Docker)

```bash
cp .env.example .env          # then set POSTGRES_PASSWORD (and DATABASE_URL to match)
docker compose up --build
```

On startup the backend container runs `alembic upgrade head` (which enables pgvector) and then starts the API.

| URL | Purpose |
|---|---|
| http://localhost:8000/health | Liveness (also at `/api/v1/health`) |
| http://localhost:8000/api/v1/ready | Readiness: PostgreSQL reachable + pgvector enabled |
| http://localhost:8000/docs | OpenAPI docs (disabled when `APP_ENV=production`) |
| `POST /api/v1/rag/search` | Shared RAG contract; returns `501 RAG_NOT_CONFIGURED` until a retriever is wired in |

```bash
curl localhost:8000/api/v1/ready
# {"status":"ready","checks":{"database":"ok","pgvector":"ok"},"pgvector_version":"0.8.x"}
```

## Tests

```bash
docker compose exec -e REQUIRE_DB_TESTS=1 backend pytest -q
```

This is the canonical full-suite command from the backend container. It collects Backend tests, Planning tests, and PostgreSQL/pgvector integration tests in the same `backend/` application-root context.
Tests marked `integration` (real PostgreSQL + pgvector) are **skipped** if the database is unreachable. Set `REQUIRE_DB_TESTS=1` to make that a failure instead (recommended in CI).

## Running without Docker

```bash
docker compose up -d postgres              # or use your own PostgreSQL with pgvector
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
pytest
```

`.env` is read from the repository root; real environment variables override it.
`DATABASE_URL` wins if set, otherwise the URL is built from `POSTGRES_*`.
Inside Compose, `POSTGRES_HOST` is forced to `postgres`.

## Migrations

```bash
cd backend
alembic upgrade head                                   # apply
alembic revision --autogenerate -m "describe change"   # new migration (after adding ORM models)
alembic upgrade head --sql                             # preview SQL without a database
```

The DB URL is never stored in `alembic.ini`; `alembic/env.py` reads it from `app.core.config`.
Revision `0001` only enables the `vector` extension - there are no tables yet because the academic schema is not final.

## Layout and boundaries

```text
API route  ->  Service  ->  Repository / RAG module / Planning module
```

```text
backend/app/
  main.py          app factory, lifespan, CORS, middleware, routers
  api/             router.py, deps.py (wiring), routes/{health,rag}.py   - no logic
  core/            config.py (only place env vars are read), logging.py, middleware.py, exceptions.py
  db/              base.py (declarative base), session.py (engine + request-scoped session), models/
  schemas/         common.py (errors, health), rag.py (shared RAG contract + metadata)
  services/        health_service.py, rag_service.py, planning_service.py (thin Planning Engine adapter)
  repositories/    health_repository.py
  rag/             interface.py (Retriever protocol), provider.py (wiring point)
  planning/        deterministic, framework-independent Planning Engine
  llm/ orchestration/              reserved integration boundaries
```

### Plugging in RAG later

Implement `app.rag.interface.Retriever` (one method: `search(RAGRequest) -> Sequence[RAGResult]`)
and return it from `app.rag.provider.get_retriever()`. The concrete retriever is still pending integration; nothing else in the backend changes.
`RAGService` already enforces `top_k`; embeddings and vector search stay entirely inside the RAG module.

### Planning Engine integration boundary

`app.services.planning_service.PlanningService` is a thin dependency-injected adapter over the public `app.planning.engine.PlanningEngine` facade. It delegates typed eligibility, audit, semester validation, candidate/ranking, single- and multi-semester planning, What-If, and UEL operations without duplicating academic logic.

Planning remains deterministic and independent of FastAPI, SQLAlchemy, PostgreSQL, RAG, and LLMs. HTTP planning routes and orchestration are not implemented yet; future API/tool layers should call `PlanningService` with the existing typed Planning contracts.

## Conventions

**Errors** - every error has one shape and never contains a stack trace:

```json
{"error": {"code": "DATABASE_UNAVAILABLE", "message": "Database connection is unavailable", "details": null}}
```

Codes so far: `VALIDATION_ERROR` (422), `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `DATABASE_UNAVAILABLE` (503),
`PGVECTOR_UNAVAILABLE` (503), `RAG_NOT_CONFIGURED` (501), `INTERNAL_SERVER_ERROR` (500).
Validation errors return only `loc`/`message`/`type` - never the submitted input.

**Logging** - one JSON object per line on stdout: `timestamp`, `level`, `module`, `message`, plus `request_path`
and `request_id` inside requests (also returned as the `X-Request-ID` header). Never log passwords, keys, secrets or
full student records.

**Config** - add new settings to `app/core/config.py` and `.env.example`; never call `os.getenv` elsewhere.
