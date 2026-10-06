"""Boundary normalization for LLM/user-supplied course codes."""

from __future__ import annotations

import re
from collections.abc import Iterable


_FORMATTING_CHARS = re.compile(r"[\s-]+")
_COURSE_CODE_SHAPE = re.compile(r"^[A-Za-z]+[0-9]+$")


def normalize_course_code(
    raw: str,
    *,
    available_codes: Iterable[str],
) -> str:
    """Resolve formatting variants to one canonical code in a trusted scope.

    The Planning domain remains responsible for strict identity validation. This
    helper only removes clear presentation formatting and selects an existing
    canonical spelling when one is available in the student's scope.
    """

    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("course code must be a non-empty string")

    key = _normalization_key(raw)
    matches = tuple(
        dict.fromkeys(
            code
            for code in available_codes
            if isinstance(code, str) and _normalization_key(code) == key
        )
    )
    if len(matches) > 1:
        raise ValueError(f"course code is ambiguous: {raw!r}")
    if matches:
        return matches[0]

    compact = _FORMATTING_CHARS.sub("", raw.strip())
    if not _COURSE_CODE_SHAPE.fullmatch(compact):
        raise ValueError(f"invalid course code format: {raw!r}")
    if compact[:4].casefold() == "asux":
        return f"ASUx{compact[4:]}"
    return compact.upper()


def _normalization_key(value: str) -> str:
    return _FORMATTING_CHARS.sub("", value.strip()).casefold()


__all__ = ["normalize_course_code"]
