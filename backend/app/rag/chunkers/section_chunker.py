from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from app.rag.chunkers.base import Chunker
from app.rag.models.domain import ChunkDraft, DocumentMetadata, ExtractedDocument

_NUMBERED_HEADING = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?|[A-Z][.)])\s+\S+")


@dataclass(frozen=True)
class Heading:
    position: int
    text: str


class SectionAwarePageChunker(Chunker):
    """
    Page-bounded chunker that prefers section / paragraph / sentence boundaries.

    Important: `min_chars` is a preferred minimum chunk size, never a reason to
    discard non-empty official text.
    """

    def __init__(self, max_chars: int = 1400, overlap_chars: int = 180, min_chars: int = 80) -> None:
        if overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")
        if min_chars <= 0:
            raise ValueError("min_chars must be positive")
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars
        self.min_chars = min_chars

    def chunk(self, document: ExtractedDocument, metadata: DocumentMetadata) -> list[ChunkDraft]:
        result: list[ChunkDraft] = []
        global_index = 0
        for page in document.pages:
            text = page.text.strip()
            if not text:
                continue
            headings = self._headings(text)
            for start, end, part in self._split_page(text, headings):
                global_index += 1
                digest = hashlib.sha256(part.encode("utf-8")).hexdigest()
                cid = f"{metadata.source_id}:P{page.page_number}:C{global_index:04d}:{digest[:8]}"
                result.append(
                    ChunkDraft(
                        chunk_id=cid,
                        source_id=metadata.source_id,
                        text=part,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        section=self._section_for_range(headings, start, end),
                        chunk_index=global_index,
                        text_hash=digest,
                    )
                )
        if not result:
            raise ValueError(f"no_chunks_created:{metadata.source_id}")
        return result

    def _headings(self, text: str) -> list[Heading]:
        headings: list[Heading] = []
        offset = 0
        for line_with_break in text.splitlines(keepends=True):
            line = line_with_break.rstrip("\r\n")
            stripped = line.strip()
            leading = len(line) - len(line.lstrip())
            if stripped and self._is_heading(stripped):
                headings.append(Heading(position=offset + leading, text=stripped[:500]))
            offset += len(line_with_break)
        return headings

    @staticmethod
    def _is_heading(line: str) -> bool:
        if len(line) > 120 or len(line) < 3:
            return False
        words = line.split()
        if len(words) > 14:
            return False
        if _NUMBERED_HEADING.match(line):
            return True
        alpha = [c for c in line if c.isalpha()]
        if alpha and line.upper() == line and len(words) <= 10:
            return True
        title_ratio = sum(1 for w in words if w[:1].isupper()) / max(len(words), 1)
        return title_ratio >= 0.8 and len(words) >= 2 and not re.search(r"[.!?]$", line)

    def _split_page(self, text: str, headings: list[Heading]) -> list[tuple[int, int, str]]:
        if len(text) <= self.max_chars:
            return [(0, len(text), text.strip())]

        heading_positions = [h.position for h in headings]
        out: list[tuple[int, int, str]] = []
        start = 0
        previous_end = -1
        min_progress = max(self.min_chars, self.overlap_chars + 1, self.max_chars // 2)

        while start < len(text):
            target = min(len(text), start + self.max_chars)
            end = target
            if target < len(text):
                lower = start + min_progress
                # Preferred order: begin next chunk at a section heading, then paragraph/line,
                # then sentence, then hard character fallback.
                heading_cuts = [p for p in heading_positions if lower <= p <= target and p > previous_end]
                if heading_cuts:
                    end = max(heading_cuts)
                else:
                    paragraph = text.rfind("\n\n", lower, target)
                    line = text.rfind("\n", lower, target)
                    sentence = text.rfind(". ", lower, target)
                    cut = max(paragraph, line, sentence)
                    if cut >= lower:
                        end = cut + (2 if text[cut : cut + 2] == ". " else 1)

            if end <= start:
                end = min(len(text), start + self.max_chars)
            part = text[start:end].strip()
            if part:
                out.append((start, end, part))
            if end >= len(text):
                break
            previous_end = end
            next_start = max(start + 1, end - self.overlap_chars)
            if next_start <= start:
                next_start = end
            start = next_start

        return out

    @staticmethod
    def _section_for_range(headings: list[Heading], start: int, end: int) -> str:
        if not headings:
            return "Unsectioned"
        inside = [h for h in headings if start <= h.position < end]
        if inside and inside[0].position - start <= 250:
            return inside[0].text
        before = [h for h in headings if h.position <= start]
        if before:
            return before[-1].text
        if inside:
            return inside[0].text
        return "Unsectioned"
