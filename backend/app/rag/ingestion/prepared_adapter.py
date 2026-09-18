from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from app.rag.models.domain import ChunkDraft, DocumentMetadata


class PreparedRagDatasetAdapter:
    """Loads a previously validated RAG preparation export (source_registry + chunks.jsonl)."""

    def __init__(self, prepared_dir: Path) -> None:
        self.root = prepared_dir
        registry = self.root / "source_registry.json"
        chunks = self.root / "chunks.jsonl"
        if not registry.exists():
            raise FileNotFoundError(f"Missing prepared source registry: {registry}")
        if not chunks.exists():
            raise FileNotFoundError(f"Missing prepared chunks file: {chunks}")

        source_rows = json.loads(registry.read_text(encoding="utf-8"))
        self.sources = {row["source_id"]: DocumentMetadata.model_validate(row) for row in source_rows}
        grouped: dict[str, list[ChunkDraft]] = defaultdict(list)
        with chunks.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    chunk = ChunkDraft.model_validate_json(line)
                except Exception as exc:
                    raise ValueError(f"Invalid prepared chunk at line {line_number}") from exc
                grouped[chunk.source_id].append(chunk)
        self.chunks = dict(grouped)

        unknown = set(self.chunks) - set(self.sources)
        if unknown:
            raise ValueError(f"Prepared chunks reference unknown source(s): {sorted(unknown)}")

    def source_ids(self) -> list[str]:
        return list(self.sources)

    def get(self, source_id: str) -> tuple[DocumentMetadata, list[ChunkDraft]]:
        if source_id not in self.sources:
            raise KeyError(f"Unknown prepared source_id: {source_id}")
        return self.sources[source_id], list(self.chunks.get(source_id, []))
