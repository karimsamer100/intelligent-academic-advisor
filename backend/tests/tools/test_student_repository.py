from __future__ import annotations

import json

import pytest

from app.planning.repositories.adapters.student_json_repository import (
    JsonStudentRepository,
    StudentRepositoryDataError,
)


def _attempt(
    student_id: str,
    course_id: str,
    *,
    passed: bool,
    credits_earned: int,
    attempt_number: int = 1,
) -> dict[str, object]:
    return {
        "student_id": student_id,
        "course_id": course_id,
        "attempt_number": attempt_number,
        "term": "Fall",
        "academic_year": 2024,
        "status": "recorded",
        "passed": passed,
        "failed": not passed,
        "withdrawn": False,
        "repeated": attempt_number > 1,
        "credits_earned": credits_earned,
    }


def _student_payload(
    *,
    student_id: str = "student-001",
    attempts: list[dict[str, object]] | None = None,
    history_coverage: str | None = "COMPLETE",
) -> dict[str, object]:
    attempts = attempts or []
    earned_credit_hours = sum(
        int(item["credits_earned"])
        for item in attempts
        if item["passed"] is True
    )
    return {
        "students": [
            {
                "student_id": student_id,
                "regulation": 2023,
                "program": "CAIE",
                "track": None,
                "course_attempts": attempts,
                "current_registrations": [],
                "academic_snapshot": {
                    "student_id": student_id,
                    "regulation": 2023,
                    "program": "CAIE",
                    "gpa": 3.0,
                    "earned_credit_hours": earned_credit_hours,
                },
                "history_coverage": history_coverage,
                "registration_coverage": "COMPLETE",
            }
        ]
    }


def _write_payload(tmp_path, payload: object):
    path = tmp_path / "students.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_repository_builds_canonical_state_from_source_attempts(tmp_path) -> None:
    student_id = "student-001"
    payload = _student_payload(
        student_id=student_id,
        attempts=[
            _attempt(student_id, "R23:CAIE:CSE121", passed=True, credits_earned=3),
            _attempt(student_id, "R23:CAIE:CSE141", passed=False, credits_earned=0),
        ],
    )

    state = JsonStudentRepository(_write_payload(tmp_path, payload)).get_student_state(
        student_id
    )

    assert state is not None
    assert state.student_id == student_id
    assert [item.course.course_id for item in state.course_attempts] == [
        "R23:CAIE:CSE121",
        "R23:CAIE:CSE141",
    ]
    assert [item.course_id for item in state.passed_courses] == ["R23:CAIE:CSE121"]
    assert state.earned_credit_hours == 3


def test_repository_returns_none_for_missing_student(tmp_path) -> None:
    path = _write_payload(tmp_path, _student_payload())

    assert JsonStudentRepository(path).get_student_state("missing") is None


def test_repository_rejects_malformed_json(tmp_path) -> None:
    path = tmp_path / "students.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(StudentRepositoryDataError):
        JsonStudentRepository(path).get_student_state("student-001")


def test_repository_rejects_invalid_source_records(tmp_path) -> None:
    payload = _student_payload(
        attempts=[
            _attempt("student-001", "not-a-course-identity", passed=True, credits_earned=3)
        ]
    )

    with pytest.raises(StudentRepositoryDataError):
        JsonStudentRepository(_write_payload(tmp_path, payload)).get_student_state(
            "student-001"
        )


def test_repository_rejects_fatal_builder_diagnostics(tmp_path) -> None:
    payload = _student_payload(history_coverage=None)

    with pytest.raises(StudentRepositoryDataError):
        JsonStudentRepository(_write_payload(tmp_path, payload)).get_student_state(
            "student-001"
        )

