from __future__ import annotations

import json
from pathlib import Path
from app.rag.extractors.base import DocumentExtractor
from app.rag.models.domain import ExtractedDocument, PageText


class FoundationExtractedTextExtractor(DocumentExtractor):
    """Loads page-preserving extraction already produced by Academic Data Foundation."""

    def extract(self, path: Path, source_id: str) -> ExtractedDocument:
        if not path.exists():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("source_id") and payload["source_id"] != source_id:
            raise ValueError(f"source_id mismatch: expected {source_id}, got {payload['source_id']}")
        if payload.get("format") != "pdf":
            raise ValueError("RAG v0 page-citation ingestion requires PDF page mapping")

        pages = [
            PageText(
                page_number=int(item["page_pdf"]),
                text=item.get("text", ""),
                raw_text=item.get("text", ""),
            )
            for item in payload.get("pages", [])
        ]
        if not pages:
            raise ValueError(f"empty_document:{path}")
        warnings = [f"empty_page:{p.page_number}" for p in pages if not p.text.strip()]
        if not any(p.text.strip() for p in pages):
            raise ValueError(f"document_contains_no_extractable_text:{path}")
        return ExtractedDocument(
            source_id=source_id,
            pages=pages,
            extraction_method="academic_data_foundation_extracted_text",
            extraction_warnings=warnings,
        )
