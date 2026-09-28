"""Temporary JSON-backed repository for development student state."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ...builders.student_state_builder import StudentStateBuildInput, StudentStateBuilder
from ...domain.academic_state import AcademicHistoryCoverage, RegistrationCoverage
from ...domain.course import CourseIdentity, Program, Regulation
from ...domain.student import StudentState
from ...domain.student_history import (
    AcademicSnapshot,
    AttemptOutcome,
    AttemptPurpose,
    CourseAttempt,
    CurrentRegistration,
)
from ..student_repository import StudentRepository, StudentRepositoryError


class StudentRepositoryDataError(StudentRepositoryError):
    """Safe error raised when the development student source is unusable."""

    def __init__(self) -> None:
        super().__init__("Student source data is unavailable or invalid")


class _RawCourseAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    student_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    term: str = Field(min_length=1)
    academic_year: int
    status: str = Field(min_length=1)
    grade: str | None = None
    grade_points: int | float | None = None
    credits_attempted: int | float | None = Field(default=None, ge=0)
    credits_earned: int | float | None = Field(default=None, ge=0)
    passed: bool | None = None
    failed: bool | None = None
    withdrawn: bool | None = None
    repeated: bool | None = None
    source: str | None = None
    outcome: AttemptOutcome | None = None
    purpose: AttemptPurpose | None = None


class _RawCurrentRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    student_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    term: str = Field(min_length=1)
    academic_year: int
    registration_status: str | None = None


class _RawAcademicSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    student_id: str = Field(min_length=1)
    regulation: int
    program: str = Field(min_length=1)
    gpa: int | float
    earned_credit_hours: int | float = Field(ge=0)
    registered_credit_hours: int | float | None = Field(default=None, ge=0)
    academic_level: str | int | None = None
    academic_standing: str | None = None
    track: str | None = None


class _RawStudent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    student_id: str = Field(min_length=1)
    regulation: int
    program: str = Field(min_length=1)
    track: str | None = None
    course_attempts: list[_RawCourseAttempt] = Field(default_factory=list)
    current_registrations: list[_RawCurrentRegistration] = Field(default_factory=list)
    academic_snapshot: _RawAcademicSnapshot | None = None
    history_coverage: AcademicHistoryCoverage | None = None
    registration_coverage: RegistrationCoverage | None = None


class _RawStudentFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    students: list[_RawStudent] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_duplicate_student_ids(self) -> "_RawStudentFile":
        student_ids = [student.student_id for student in self.students]
        if len(student_ids) != len(set(student_ids)):
            raise ValueError("student IDs must be unique")
        return self


class JsonStudentRepository(StudentRepository):
    """Load source records and build canonical ``StudentState`` values."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a pathlib.Path")
        self._path = path

    @classmethod
    def from_settings(cls) -> "JsonStudentRepository":
        """Create the repository from centralized application settings."""

        from app.core.config import get_settings

        return cls(get_settings().student_data_path)

    def get_student_state(self, student_id: str) -> StudentState | None:
        if not isinstance(student_id, str) or not student_id.strip():
            raise StudentRepositoryDataError()

        student_file = self._load_file()
        raw_student = next(
            (student for student in student_file.students if student.student_id == student_id),
            None,
        )
        if raw_student is None:
            return None

        try:
            build_result = StudentStateBuilder().build(_to_build_input(raw_student))
        except (TypeError, ValueError):
            raise StudentRepositoryDataError() from None

        if build_result.student_state is None:
            raise StudentRepositoryDataError()
        return build_result.student_state

    def _load_file(self) -> _RawStudentFile:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                payload = {"students": payload}
            return _RawStudentFile.model_validate(payload)
        except (OSError, json.JSONDecodeError, TypeError, ValidationError):
            raise StudentRepositoryDataError() from None


def _to_build_input(raw_student: _RawStudent) -> StudentStateBuildInput:
    regulation = Regulation.from_year(raw_student.regulation)
    program = Program(raw_student.program)
    snapshot = raw_student.academic_snapshot

    return StudentStateBuildInput(
        student_id=raw_student.student_id,
        regulation=regulation,
        program=program,
        track=raw_student.track,
        course_attempts=tuple(_to_attempt(item) for item in raw_student.course_attempts),
        current_registrations=tuple(
            _to_registration(item) for item in raw_student.current_registrations
        ),
        academic_snapshot=_to_snapshot(snapshot) if snapshot is not None else None,
        history_coverage=raw_student.history_coverage,
        registration_coverage=raw_student.registration_coverage,
    )


def _to_attempt(raw: _RawCourseAttempt) -> CourseAttempt:
    return CourseAttempt(
        student_id=raw.student_id,
        course=CourseIdentity.parse(raw.course_id),
        attempt_number=raw.attempt_number,
        term=raw.term,
        academic_year=raw.academic_year,
        status=raw.status,
        grade=raw.grade,
        grade_points=raw.grade_points,
        credits_attempted=raw.credits_attempted,
        credits_earned=raw.credits_earned,
        passed=raw.passed,
        failed=raw.failed,
        withdrawn=raw.withdrawn,
        repeated=raw.repeated,
        source=raw.source,
        outcome=raw.outcome,
        purpose=raw.purpose,
    )


def _to_registration(raw: _RawCurrentRegistration) -> CurrentRegistration:
    return CurrentRegistration(
        student_id=raw.student_id,
        course=CourseIdentity.parse(raw.course_id),
        term=raw.term,
        academic_year=raw.academic_year,
        registration_status=raw.registration_status,
    )


def _to_snapshot(raw: _RawAcademicSnapshot) -> AcademicSnapshot:
    return AcademicSnapshot(
        student_id=raw.student_id,
        regulation=Regulation.from_year(raw.regulation),
        program=Program(raw.program),
        gpa=raw.gpa,
        earned_credit_hours=raw.earned_credit_hours,
        registered_credit_hours=raw.registered_credit_hours,
        academic_level=raw.academic_level,
        academic_standing=raw.academic_standing,
        track=raw.track,
    )


__all__ = ["JsonStudentRepository", "StudentRepositoryDataError"]
