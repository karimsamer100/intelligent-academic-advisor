from fastapi.testclient import TestClient

from app.api.dependencies import get_rag_service
from app.main import app
from app.rag.models.domain import RetrievedEvidence
from app.schemas.rag import RAGSearchResponse

client = TestClient(app)


def test_root_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_versioned_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_contract_without_real_db(monkeypatch):
    import app.api.routes.health as health_routes

    monkeypatch.setattr(
        health_routes,
        "database_readiness",
        lambda _: {"database": "ok", "pgvector": "ok", "pgvector_version": "0.8.6"},
    )
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["pgvector"] == "ok"


def test_rag_search_route_uses_service_boundary():
    class FakeService:
        def search(self, request):
            assert request.regulation == 2023  # short form 23 is normalized
            return RAGSearchResponse(
                results=[
                    RetrievedEvidence(
                        chunk_id="C1",
                        text="Evidence",
                        score=0.9,
                        source_id="S1",
                        file_name="Bylaw.pdf",
                        page_start=8,
                        page_end=8,
                        section="Registration Rules",
                        document_type="REGULATION",
                        regulation=2023,
                        program=None,
                        language="en",
                        topic="credit_load",
                    )
                ]
            )

    app.dependency_overrides[get_rag_service] = lambda: FakeService()
    try:
        response = client.post(
            "/api/v1/rag/search",
            json={
                "query": "What is the maximum credit load?",
                "regulation": 23,
                "document_types": ["REGULATION"],
                "language": "en",
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["source_id"] == "S1"
    assert body["results"][0]["page_start"] == 8
