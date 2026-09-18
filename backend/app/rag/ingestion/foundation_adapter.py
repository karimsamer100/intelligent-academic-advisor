from __future__ import annotations

import json
from pathlib import Path
from app.rag.models.domain import DocumentMetadata


class AcademicDataFoundationAdapter:
    """Adapter for the delivered Academic Data Foundation package."""

    def __init__(self, foundation_root: Path) -> None:
        self.root = foundation_root
        registry_path = self.root / "rag" / "source_registry.json"
        if not registry_path.exists():
            raise FileNotFoundError(f"Missing RAG source registry: {registry_path}")
        self._sources = json.loads(registry_path.read_text(encoding="utf-8"))
        self._by_id = {row["source_id"]: row for row in self._sources}

    def list_sources(self, rag_recommended_only: bool = True) -> list[dict]:
        rows = self._sources
        if rag_recommended_only:
            rows = [x for x in rows if x.get("rag_ingest_recommended")]
        return list(rows)

    def get_raw(self, source_id: str) -> dict:
        try:
            return self._by_id[source_id]
        except KeyError as exc:
            raise KeyError(f"Unknown source_id: {source_id}") from exc

    def metadata(self, source_id: str) -> DocumentMetadata:
        src = self.get_raw(source_id)
        document_type = src.get("document_type")
        document_types = list(src.get("document_types") or ([document_type] if document_type else []))
        title = src.get("document_title") or Path(src["file_name"]).stem
        return DocumentMetadata(
            source_id=src["source_id"],
            file_name=src["file_name"],
            document_title=title,
            document_types=document_types,
            regulations=list(src.get("regulations") or []),
            programs=list(src.get("programs") or []),
            languages=list(src.get("languages") or []),
            effective_year=src.get("effective_year"),
            version=src.get("version"),
            official_status=src["official_status"],
            file_hash=src["sha256"],
            relative_path=src.get("relative_path"),
            authority_level=src.get("authority_level"),
            verification_state="SOURCE_SNAPSHOT_VERIFIED",
            page_count=src.get("page_count"),
            source_metadata={
                "classification": src.get("classification"),
                "project_role": src.get("project_role"),
                "project_priority": src.get("project_priority"),
                "authority_precedence": src.get("authority_precedence"),
                "duplicate_or_superseded_by": src.get("duplicate_or_superseded_by"),
                "notes": src.get("notes"),
                "original_document_type": document_type,
            },
        )

    def document_path(self, source_id: str) -> Path:
        src = self.get_raw(source_id)
        relative = src.get("relative_path")
        if not relative:
            raise ValueError(f"No relative_path for {source_id}")
        return self.root / relative

    def extracted_text_path(self, source_id: str) -> Path:
        return self.root / "raw" / "extracted_text" / f"{source_id}.json"
