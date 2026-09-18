#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings
from app.db.session import session_scope
from app.rag.embeddings.sentence_transformer import SentenceTransformerEmbeddingProvider
from app.rag.repositories.pgvector_repository import PgVectorChunkRepository
from app.rag.retrieval.service import DocumentSearchService


def main() -> int:
    settings = get_settings()
    cases = json.loads((ROOT / "data" / "smoke_tests" / "rag_smoke_tests.json").read_text(encoding="utf-8"))
    embedder = SentenceTransformerEmbeddingProvider(
        settings.embedding_model, settings.embedding_device, settings.embedding_dimension,
        settings.embedding_cache_dir, settings.embedding_batch_size,
    )
    report = []
    failures = 0
    with session_scope() as session:
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
            if status.startswith("FAIL"):
                failures += 1
            report.append({
                "case_id": case["case_id"],
                "status": status,
                "top_results": [
                    {"source_id": r.source_id, "page_start": r.page_start, "page_end": r.page_end, "score": r.score}
                    for r in results[:5]
                ],
            })
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
