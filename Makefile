.PHONY: up down build logs test migrate ingest-sample smoke

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f backend

test:
	cd backend && pytest -q -m "not integration"

migrate:
	docker compose exec backend alembic upgrade head

ingest-sample:
	docker compose exec backend python -m app.rag.ingestion.cli ingest-prepared --prepared-dir /app/data/prepared_sample

smoke:
	docker compose exec backend python /app/scripts/run_rag_smoke_tests.py
