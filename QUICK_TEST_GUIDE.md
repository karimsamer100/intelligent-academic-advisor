# Quick Test Guide (Windows-friendly)

Run these commands from the project root.

## 1. Create environment file

```powershell
Copy-Item .env.example .env
```

## 2. Start the backend and PostgreSQL/pgvector

```powershell
docker compose up -d --build
```

Check:

```text
http://localhost:8000/health
http://localhost:8000/api/v1/ready
http://localhost:8000/docs
```

## 3. Ingest the included three-source proof set

```powershell
docker compose exec backend python -m app.rag.ingestion.cli ingest-prepared --prepared-dir /app/data/prepared_sample
```

The first real embedding operation uses the local `BAAI/bge-m3` embedding model. The Docker volume keeps the downloaded model cache for later runs.

## 4. Search from the CLI

```powershell
docker compose exec backend python -m app.rag.ingestion.cli search "How many credits can a student with a GPA of at least 3 register in a main semester?" --regulation 2023 --document-type REGULATION --language en --top-k 5
```

## 5. Search from the API

Open `http://localhost:8000/docs`, then use `POST /api/v1/rag/search` with:

```json
{
  "query": "How many credits can a student with a GPA of at least 3 register in a main semester?",
  "regulation": 23,
  "document_types": ["REGULATION"],
  "language": "en",
  "top_k": 5
}
```

## 6. Run tests

```powershell
docker compose exec backend pytest -q -m "not integration"
```

```powershell
docker compose exec -e RUN_PGVECTOR_TESTS=1 backend pytest -q -m integration
```

```powershell
docker compose exec backend python /app/scripts/run_rag_smoke_tests.py
```

## 7. Optional: install the full Academic Data Foundation

If you have `Academic_Data_Foundation_SUBMISSION_READY.zip`:

```powershell
python scripts/unpack_academic_foundation.py "C:\path\to\Academic_Data_Foundation_SUBMISSION_READY.zip"
```

Then ingest all RAG-recommended official sources:

```powershell
docker compose exec backend python -m app.rag.ingestion.cli ingest-foundation --foundation-path /app/data/academic_foundation --all-rag-sources
```
