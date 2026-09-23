#!/usr/bin/env python3
from __future__ import annotations

import json
import argparse
import importlib.util
from uuid import uuid4
from contextlib import contextmanager
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings
from app.db.session import session_scope
from app.rag.embeddings.sentence_transformer import SentenceTransformerEmbeddingProvider
from app.rag.repositories.pgvector_repository import PgVectorChunkRepository
from app.rag.retrieval.service import DocumentSearchService


@contextmanager
def smoke_session(prepared_dir, embedder):
    """Optionally prove the final code against a fresh corpus; rollback all proof data."""
    with session_scope() as session:
        ingestion = []
        if prepared_dir:
            from alembic.migration import MigrationContext
            from alembic.operations import Operations
            from sqlalchemy import text
            from app.rag.ingestion.cli import _common_pipeline
            from app.rag.ingestion.prepared_adapter import PreparedRagDatasetAdapter

            schema = "rag_proof_" + uuid4().hex
            session.execute(text(f'CREATE SCHEMA "{schema}"'))
            session.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            path = ROOT / "backend/alembic/versions/0001_rag_pgvector.py"
            spec = importlib.util.spec_from_file_location("rag_proof_migration", path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(session.connection())):
                migration.upgrade()
            adapter = PreparedRagDatasetAdapter(prepared_dir)
            pipeline = _common_pipeline(None, embedder, PgVectorChunkRepository(session))
            for sid in adapter.source_ids():
                source, chunks = adapter.get(sid)
                ingestion.append(pipeline.ingest_prepared(source, chunks).model_dump(mode="json"))
        try:
            yield session, ingestion
        finally:
            if prepared_dir:
                session.rollback()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prepared-dir", type=Path, help="Ingest and evaluate in an isolated rollback-only schema")
    args = parser.parse_args()
    settings = get_settings()
    cases = json.loads((ROOT / "data" / "smoke_tests" / "rag_smoke_tests.json").read_text(encoding="utf-8"))
    embedder = SentenceTransformerEmbeddingProvider(
        settings.embedding_model, settings.embedding_device, settings.embedding_dimension,
        settings.embedding_cache_dir, settings.embedding_batch_size,
    )
    report = []
    failures = 0
    with smoke_session(args.prepared_dir, embedder) as (session, ingestion):
        service = DocumentSearchService(embedder, PgVectorChunkRepository(session), settings.rag_top_k, settings.rag_max_top_k, settings.rag_min_score)
        for case in cases:
            results = service.search_documents(case["query"], top_k=5, **case.get("filters", {}))
            if case.get("expected_source") is None:
                if case.get("requires_min_score") and settings.rag_min_score is None:
                    status = "MANUAL_REVIEW_SET_RAG_MIN_SCORE"
                else:
                    status = "PASS" if not results else "FAIL"
            else:
                status = "FAIL"
                for result in results:
                    if result.source_id == case["expected_source"] and result.page_start <= case["expected_page"] <= result.page_end:
                        status = "PASS"
                        break
                forbidden = case.get("forbidden_source")
                if forbidden and any(r.source_id == forbidden for r in results):
                    status = "FAIL_CROSS_CONTAMINATION"
                expected_regulation = case.get("expected_regulation")
                if expected_regulation is not None and any(
                    r.regulation is not None and r.regulation != expected_regulation for r in results
                ):
                    status = "FAIL_CROSS_CONTAMINATION"
            if status.startswith("FAIL"):
                failures += 1
            report.append({
                "case_id": case["case_id"],
                "status": status,
                "query": case["query"],
                "filters": case.get("filters", {}),
                "top_results": [
                    r.model_dump(mode="json")
                    for r in results[:5]
                ],
            })
            # Measure semantic distractors separately from the trusted-filter acceptance check.
            if case.get("forbidden_source"):
                unfiltered = service.search_documents(case["query"], top_k=20)
                report[-1]["unfiltered_distractors"] = [r.model_dump(mode="json") for r in unfiltered
                    if r.source_id == case["forbidden_source"]]
    pending = sum(r["status"].startswith("MANUAL") for r in report)
    payload = {"model": embedder.model_name, "dimension": embedder.dimension,
               "corpus": "isolated_prepared_proof" if args.prepared_dir else "existing_database",
               "proof_ingestion": ingestion,
               "min_score": settings.rag_min_score, "passed": sum(r["status"] == "PASS" for r in report),
               "failed": failures, "pending": pending, "cases": report}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 1 if failures else (2 if pending else 0)


if __name__ == "__main__":
    raise SystemExit(main())
