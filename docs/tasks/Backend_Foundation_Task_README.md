# Backend Foundation Task

**Project:** Local Intelligent Academic Advisor  
**Task:** Backend Foundation  
**Goal:** Build a clean and runnable backend foundation that future RAG, Planning Engine, LLM, orchestration, and frontend work can integrate with without restructuring the project.

---

## 1. Scope

Build the backend infrastructure only:

- FastAPI application structure
- centralized configuration
- PostgreSQL connection
- pgvector availability
- SQLAlchemy setup
- Alembic migrations
- Docker-based local environment
- API conventions
- logging and error handling
- health/readiness endpoints
- shared RAG request/response schemas
- clean service/module boundaries
- basic backend tests

Do **not** implement academic advising logic in this task.

The Planning Engine will be developed after the Academic Data Foundation is finalized.

---

## 2. Locked Decisions

Use:

- Python
- FastAPI
- PostgreSQL
- pgvector inside PostgreSQL
- SQLAlchemy
- Alembic
- Docker Compose
- `.env` / environment-based configuration

Important rules:

- Current Excel workbook is not the final runtime schema.
- Do not hard-code Regulation 18/23 academic rules.
- Do not add cloud LLM APIs.
- Do not implement the frontend here.
- RAG and Planning Engine must remain separate modules behind clean interfaces.

---

## 3. Repository Structure

Recommended structure:

```text
intelligent-academic-advisor/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── router.py
│   │   │   └── routes/
│   │   │       ├── health.py
│   │   │       └── rag.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   └── exceptions.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── models/
│   │   ├── schemas/
│   │   │   ├── common.py
│   │   │   └── rag.py
│   │   ├── services/
│   │   │   ├── rag_service.py
│   │   │   └── planning_service.py
│   │   ├── repositories/
│   │   ├── rag/
│   │   ├── planning/
│   │   ├── llm/
│   │   └── orchestration/
│   ├── tests/
│   ├── alembic/
│   ├── alembic.ini
│   ├── Dockerfile
│   └── requirements.txt
│
├── data/
├── docs/
├── scripts/
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

Empty future folders are acceptable. Do not add fake implementations.

---

## 4. FastAPI Foundation

Create:

- central `main.py`
- versioned API prefix such as `/api/v1`
- central router
- application lifespan/startup handling
- CORS configured from environment variables
- OpenAPI docs enabled for development

Minimum endpoints:

```text
GET /health
GET /api/v1/health
GET /api/v1/ready
```

`/health` confirms the API process is alive.

`/ready` confirms required infrastructure such as PostgreSQL is reachable.

---

## 5. Configuration

Use one typed configuration layer.

Expected variables:

```text
APP_ENV
APP_NAME
APP_HOST
APP_PORT
API_V1_PREFIX

DATABASE_URL

POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_HOST
POSTGRES_PORT

RAG_TOP_K
DOCUMENTS_PATH

LOG_LEVEL
CORS_ORIGINS
```

Create `.env.example` with placeholders.

Do not scatter `os.getenv()` calls across the codebase.

Never commit credentials.

---

## 6. PostgreSQL + pgvector

PostgreSQL is the main DB.

Enable:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

The project must be able to verify that pgvector is available.

Do **not** design the final academic schema yet.

The Academic Data Foundation is still being finalized.

Infrastructure-level tables are allowed when genuinely needed.

---

## 7. SQLAlchemy

Set up:

- SQLAlchemy 2.x style
- declarative base
- request-scoped DB sessions
- clean repository/service boundaries

Do not put business logic inside ORM models.

---

## 8. Alembic

Configure Alembic from the beginning.

Required:

- migrations folder
- working `alembic upgrade head`
- DB URL from centralized configuration
- initial migration only if actual tables are needed

Do not rely on manual DB table creation.

---

## 9. Docker

Create a local Docker setup with at least:

```text
backend
postgres
```

PostgreSQL image must support pgvector.

Expected developer flow:

```bash
docker compose up --build
```

After startup:

- backend responds
- PostgreSQL is reachable
- pgvector is enabled
- migrations can run

Avoid adding unnecessary services.

---

## 10. Backend Boundaries

Routes should not contain core logic.

Preferred flow:

```text
API Route
   ↓
Service
   ↓
Repository / RAG / Planning module
```

Create a real `RAGService` boundary.

A `PlanningService` placeholder/interface may exist if useful, but no planning logic should be implemented now.

---

## 11. Shared RAG Request Contract

Recommended Pydantic request:

```json
{
  "query": "What is the maximum credit load?",
  "student_id": null,
  "regulation": 23,
  "program": "CAIE",
  "document_types": ["REGULATION"],
  "language": "en",
  "top_k": 5
}
```

Fields:

```text
query: required string
student_id: optional string
regulation: optional integer
program: optional string
document_types: optional list[string]
language: optional string
top_k: positive integer
```

Trusted profile context should be preferred over free-text inference when available.

---

## 12. Shared RAG Response Contract

Recommended response:

```json
{
  "results": [
    {
      "chunk_id": "CHK-001",
      "text": "...",
      "score": 0.88,
      "source_id": "SRC-001",
      "file_name": "Bylaw 2023.pdf",
      "page_start": 42,
      "page_end": 42,
      "section": "Registration Rules",
      "document_type": "REGULATION",
      "regulation": 23,
      "program": "CAIE",
      "language": "en"
    }
  ]
}
```

The backend must not need to know how the embedding or vector-search implementation works.

---

## 13. Shared Metadata

### Document-level

```text
source_id
file_name
document_title
document_types[]
regulations[]
programs[]
languages[]
effective_year
version
official_status
file_hash
```

A document may have multiple document types, regulations, programs, and languages.

### Chunk-level

```text
chunk_id
source_id
text
page_start
page_end
section
document_type
regulation
program
language
topic
chunk_index
```

Chunk-level metadata should narrow the document scope when possible.

---

## 14. Errors

Use one consistent error format.

Example:

```json
{
  "error": {
    "code": "DATABASE_UNAVAILABLE",
    "message": "Database connection is unavailable",
    "details": null
  }
}
```

Add central exception handlers.

Do not expose raw stack traces to clients.

---

## 15. Logging

Use structured application logging.

Minimum:

- timestamp
- level
- module
- request path
- useful error context

Never log:

- passwords
- API keys
- secrets
- full sensitive student records

---

## 16. Basic Tests

Add only the tests needed to protect the backend foundation.

Minimum:

- health endpoint
- readiness endpoint
- config loading
- DB connectivity
- pgvector extension check
- RAG request schema validation
- RAG response schema validation

Use `pytest`.

This is not the final project evaluation system.

---

## 17. Do Not Implement Yet

Do not implement:

- course eligibility
- prerequisite logic
- academic planning
- final academic DB schema
- final student-history schema
- local LLM runtime
- LLM orchestration
- RAG extraction/chunking/embedding logic
- frontend
- voice
- full authentication
- advisor workflow

---

## 18. Definition of Done

The task is complete when:

1. Repository can be cloned and configured from `.env.example`.
2. `docker compose up --build` starts FastAPI + PostgreSQL.
3. Health endpoint works.
4. Readiness endpoint confirms DB connectivity.
5. pgvector is enabled.
6. SQLAlchemy is configured.
7. Alembic works.
8. Shared RAG request/response schemas exist.
9. Basic error/logging setup exists.
10. Basic backend tests pass.
11. No academic rules are hard-coded.
12. Codebase is ready for RAG integration and later Planning Engine integration.

---

## 19. Deliverable

Submit a PR containing:

```text
FastAPI application
PostgreSQL + pgvector setup
SQLAlchemy configuration
Alembic configuration
Dockerfile / docker-compose integration
.env.example
health/readiness routes
shared RAG schemas
basic error/logging setup
basic tests
short run instructions
```

Keep the task focused on foundation, not product features.
