from __future__ import annotations

import re
from app.rag.metadata.taxonomy import TOPIC_KEYWORDS, canonical_document_type
from app.rag.models.domain import ChunkDraft, DocumentMetadata

_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_LATIN_RE = re.compile(r"[A-Za-z]")


class MetadataEnricher:
    """Narrows chunk metadata without inventing unsupported academic facts."""

    def enrich(self, chunk: ChunkDraft, source: DocumentMetadata) -> ChunkDraft:
        canonical_types = list(dict.fromkeys(canonical_document_type(x) for x in source.document_types if canonical_document_type(x)))
        chunk.document_type = self.infer_document_type(chunk.text, canonical_types)
        chunk.applicable_document_types = canonical_types
        chunk.language = self.detect_language(chunk.text)
        chunk.regulation = self.infer_regulation(chunk.text, source.regulations)
        chunk.program = self.infer_program(chunk.text, source.programs)
        chunk.applicable_regulations = list(dict.fromkeys(source.regulations))
        chunk.applicable_programs = list(dict.fromkeys(source.programs))
        chunk.topic = self.infer_topic(chunk.text)
        chunk.metadata = {
            **chunk.metadata,
            "source_document_types": source.document_types,
            "source_regulations": source.regulations,
            "source_programs": source.programs,
            "metadata_scope_note": self._scope_note(chunk, source),
        }
        return chunk


    @staticmethod
    def infer_document_type(text: str, source_types: list[str]) -> str | None:
        if len(source_types) == 1:
            return source_types[0]
        if not source_types:
            return None
        lower = text.casefold()
        hints = {
            "REGULATION": ("bylaw", "regulation", "academic rule", "registration rules"),
            "PROCEDURE": ("procedure", "steps", "guideline", "upload", "submission"),
            "COURSE_HANDBOOK": ("course handbook", "course title", "course code", "credit hours"),
            "MODULE_SPEC": ("module specification", "module learning outcomes", "module title"),
            "TRAINING_HANDBOOK": ("training", "industrial training", "field training"),
        }
        matched = [t for t in source_types if any(k in lower for k in hints.get(t, ())) ]
        return matched[0] if len(set(matched)) == 1 else None

    @staticmethod
    def detect_language(text: str) -> str:
        arabic = len(_ARABIC_RE.findall(text))
        latin = len(_LATIN_RE.findall(text))
        total = arabic + latin
        if total == 0:
            return "und"
        ar_ratio = arabic / total
        en_ratio = latin / total
        if ar_ratio >= 0.2 and en_ratio >= 0.2:
            return "mixed"
        return "ar" if ar_ratio > en_ratio else "en"

    @staticmethod
    def infer_regulation(text: str, source_regulations: list[int]) -> int | None:
        if len(source_regulations) == 1:
            return source_regulations[0]
        lowered = text.casefold()
        mentions: list[int] = []
        for reg in source_regulations:
            year = str(reg)
            short = year[-2:]
            patterns = (
                rf"\bbylaw\s*[-:]?\s*{year}\b",
                rf"\bregulation(?:s)?\s*[-:]?\s*{year}\b",
                rf"\b{year}\s+bylaw\b",
                rf"\bug\s*{year}\b",
                rf"\b{short}p\b",
            )
            if any(re.search(pattern, lowered) for pattern in patterns):
                mentions.append(reg)
        return mentions[0] if len(set(mentions)) == 1 else None

    @staticmethod
    def infer_program(text: str, source_programs: list[str]) -> str | None:
        if len(source_programs) == 1:
            return source_programs[0]
        upper = text.upper()
        found = [p for p in source_programs if re.search(rf"\b{re.escape(p.upper())}\b", upper)]
        return found[0] if len(set(found)) == 1 else None

    @staticmethod
    def infer_topic(text: str) -> str:
        lower = text.casefold()
        scored: list[tuple[int, str]] = []
        for topic, keywords in TOPIC_KEYWORDS.items():
            score = sum(lower.count(keyword) for keyword in keywords)
            if score:
                scored.append((score, topic))
        if not scored:
            return "general"
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[0][1]

    @staticmethod
    def _scope_note(chunk: ChunkDraft, source: DocumentMetadata) -> str:
        notes = []
        if len(source.regulations) > 1 and chunk.regulation is None:
            notes.append("regulation_not_narrowed; applicability inherited explicitly from source registry")
        if len(source.programs) > 1 and chunk.program is None:
            notes.append("program_not_narrowed; applicability inherited explicitly from source registry")
        if not source.programs:
            notes.append("program_applicability_unscoped_in_source_registry")
        return "; ".join(notes) or "chunk_scope_is_source_supported"
