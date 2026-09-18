from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_rag_service
from app.core.exceptions import AppError
from app.schemas.rag import RAGSearchRequest, RAGSearchResponse
from app.services.rag_service import RAGService

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/search", response_model=RAGSearchResponse)
def search_rag(
    request: RAGSearchRequest,
    service: RAGService = Depends(get_rag_service),
) -> RAGSearchResponse:
    try:
        return service.search(request)
    except ValueError as exc:
        raise AppError(
            code="RAG_REQUEST_INVALID",
            message=str(exc),
            status_code=400,
        ) from exc
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="RAG_UNAVAILABLE",
            message="RAG retrieval is temporarily unavailable",
            status_code=503,
        ) from exc
