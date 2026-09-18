from __future__ import annotations

import logging
from pathlib import Path
import fitz
from app.rag.extractors.base import DocumentExtractor
from app.rag.models.domain import ExtractedDocument, PageText

logger = logging.getLogger(__name__)


class PyMuPDFExtractor(DocumentExtractor):
    """PDF extractor that preserves one-based PDF page provenance."""

    def extract(self, path: Path, source_id: str) -> ExtractedDocument:
        if not path.exists():
            raise FileNotFoundError(path)
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"PyMuPDFExtractor only supports PDF files: {path}")

        pages: list[PageText] = []
        warnings: list[str] = []
        try:
            with fitz.open(path) as doc:
                for index, page in enumerate(doc, start=1):
                    text = page.get_text("text", sort=True) or ""
                    if not text.strip():
                        warning = f"empty_page:{index}"
                        warnings.append(warning)
                        logger.warning("Empty PDF page", extra={"source_id": source_id, "page": index})
                    pages.append(PageText(page_number=index, text=text, raw_text=text))
        except Exception as exc:
            raise RuntimeError(f"PDF extraction failed for {path}: {exc}") from exc

        if not pages:
            raise ValueError(f"empty_document:{path}")
        if not any(p.text.strip() for p in pages):
            raise ValueError(f"document_contains_no_extractable_text:{path}")

        logger.info("Source extracted", extra={"source_id": source_id, "page_count": len(pages)})
        return ExtractedDocument(
            source_id=source_id,
            pages=pages,
            extraction_method="pymupdf",
            extraction_warnings=warnings,
        )
