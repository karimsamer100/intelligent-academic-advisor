from __future__ import annotations
from abc import ABC, abstractmethod
from app.rag.models.domain import ChunkDraft, DocumentMetadata, ExtractedDocument


class Chunker(ABC):
    @abstractmethod
    def chunk(self, document: ExtractedDocument, metadata: DocumentMetadata) -> list[ChunkDraft]:
        raise NotImplementedError
