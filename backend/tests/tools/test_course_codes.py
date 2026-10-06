from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.course_codes import normalize_course_code


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CSE221", "CSE221"),
        ("cse221", "CSE221"),
        ("Cse221", "CSE221"),
        ("CSE 221", "CSE221"),
        ("  CSE221  ", "CSE221"),
    ],
)
def test_normalize_course_code_accepts_clear_cse221_formatting_variants(
    raw: str,
    expected: str,
) -> None:
    assert normalize_course_code(raw, available_codes=("CSE221",)) == expected


def test_normalize_course_code_treats_cse_hyphen_as_formatting() -> None:
    assert normalize_course_code("CSE-221", available_codes=("CSE221",)) == "CSE221"


def test_normalize_course_code_preserves_real_asux_canonical_spelling() -> None:
    courses_path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "academic"
        / "normalized"
        / "courses.json"
    )
    records = json.loads(courses_path.read_text(encoding="utf-8"))
    available_codes = tuple(
        record["course_code"]
        for record in records
        if record.get("course_code") != "-"
    )

    assert "ASUx31" in available_codes
    for raw in ("ASUx31", "asux31", "ASUX31", "asu x31", "ASU X31"):
        assert (
            normalize_course_code(raw, available_codes=available_codes) == "ASUx31"
        )


def test_normalize_course_code_does_not_guess_unknown_course() -> None:
    assert normalize_course_code("CSE9999", available_codes=("CSE221",)) == "CSE9999"


def test_normalize_course_code_rejects_normalization_collisions() -> None:
    with pytest.raises(ValueError, match="ambiguous"):
        normalize_course_code(
            "CSE221",
            available_codes=("CSE221", "CSE-221"),
        )
