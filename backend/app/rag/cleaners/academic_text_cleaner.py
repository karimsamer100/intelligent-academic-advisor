from __future__ import annotations

from collections import Counter
import re
from app.rag.cleaners.base import TextCleaner
from app.rag.models.domain import ExtractedDocument, PageText

_BULLET_RE = re.compile(r"^(?:[-•▪◦*]|\(?[A-Za-z0-9]+[.)])\s+")


def _key(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip()).casefold()


class AcademicTextCleaner(TextCleaner):
    """Conservative cleaner: formatting only, never summarization or rewriting."""

    def __init__(self, boilerplate_edge_lines: int = 2, repeated_ratio: float = 0.5) -> None:
        self.boilerplate_edge_lines = boilerplate_edge_lines
        self.repeated_ratio = repeated_ratio

    def clean(self, document: ExtractedDocument) -> ExtractedDocument:
        repeated = self._repeated_edge_lines(document)
        pages: list[PageText] = []
        for page in document.pages:
            raw = page.raw_text if page.raw_text is not None else page.text
            lines = [self._normalize_line(x) for x in raw.splitlines()]
            lines = [x for x in lines if x]
            lines = self._strip_repeated_edges(lines, repeated)
            text = self._merge_broken_lines(lines)
            pages.append(PageText(page_number=page.page_number, text=text, raw_text=raw))
        return ExtractedDocument(
            source_id=document.source_id,
            pages=pages,
            extraction_method=document.extraction_method,
            extraction_warnings=document.extraction_warnings,
        )

    def _repeated_edge_lines(self, document: ExtractedDocument) -> set[str]:
        counts: Counter[str] = Counter()
        nonempty_pages = 0
        for page in document.pages:
            lines = [self._normalize_line(x) for x in page.text.splitlines()]
            lines = [x for x in lines if x]
            if not lines:
                continue
            nonempty_pages += 1
            edge = lines[: self.boilerplate_edge_lines] + lines[-self.boilerplate_edge_lines :]
            for line in set(edge):
                if len(line) <= 160:
                    counts[_key(line)] += 1
        threshold = max(3, int(nonempty_pages * self.repeated_ratio + 0.999))
        return {line for line, count in counts.items() if count >= threshold and line}

    @staticmethod
    def _normalize_line(line: str) -> str:
        line = line.replace("\u00a0", " ").replace("\ufeff", "")
        return re.sub(r"[ \t]+", " ", line).strip()

    def _strip_repeated_edges(self, lines: list[str], repeated: set[str]) -> list[str]:
        if not repeated:
            return lines
        start = 0
        while start < min(self.boilerplate_edge_lines + 1, len(lines)) and _key(lines[start]) in repeated:
            start += 1
        end = len(lines)
        removed = 0
        while end > start and removed < self.boilerplate_edge_lines + 1 and _key(lines[end - 1]) in repeated:
            end -= 1
            removed += 1
        return lines[start:end]

    @staticmethod
    def _merge_broken_lines(lines: list[str]) -> str:
        if not lines:
            return ""
        merged: list[str] = []
        for line in lines:
            if not merged:
                merged.append(line)
                continue
            prev = merged[-1]
            safe_join = (
                not _BULLET_RE.match(line)
                and not _BULLET_RE.match(prev)
                and not re.search(r"[.!?:;]$", prev)
                and line[:1].islower()
                and len(prev) + len(line) < 500
            )
            if safe_join:
                merged[-1] = prev + " " + line
            else:
                merged.append(line)
        return "\n".join(merged).strip()
