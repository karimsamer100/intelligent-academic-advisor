from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_rag_service
from app.schemas.common import ErrorResponse
from app.schemas.rag import RAGRequest, RAGResponse
from app.services.rag_service import RAGService

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post(
    "/search",
    response_model=RAGResponse,
    summary="Retrieve relevant document chunks",
    responses={501: {"model": ErrorResponse, "description": "No RAG retriever is configured yet"}},
)
def search(payload: RAGRequest, service: Annotated[RAGService, Depends(get_rag_service)]) -> RAGResponse:
    return service.search(payload)
