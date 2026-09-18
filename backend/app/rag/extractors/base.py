from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from app.rag.models.domain import ExtractedDocument


class DocumentExtractor(ABC):
    @abstractmethod
    def extract(self, path: Path, source_id: str) -> ExtractedDocument:
        raise NotImplementedError
