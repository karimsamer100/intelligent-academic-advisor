from __future__ import annotations
from abc import ABC, abstractmethod
from app.rag.models.domain import ExtractedDocument


class TextCleaner(ABC):
    @abstractmethod
    def clean(self, document: ExtractedDocument) -> ExtractedDocument:
        raise NotImplementedError
