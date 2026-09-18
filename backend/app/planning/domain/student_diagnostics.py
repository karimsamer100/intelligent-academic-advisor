"""Structured diagnostics produced while constructing student state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .course import CourseIdentity
from .reasons import ReasonCode
from .student import StudentState


class StudentStateDiagnosticCode(StrEnum):
    """Machine-readable quality findings for supplied student records."""

    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    DUPLICATE_RECORD = "DUPLICATE_RECORD"
    CONTRADICTORY_RECORD = "CONTRADICTORY_RECORD"
    INCOMPLETE_RECORD = "INCOMPLETE_RECORD"
    CREDIT_DATA_CONFLICT = "CREDIT_DATA_CONFLICT"


class DiagnosticSeverity(StrEnum):
    WARNING = "WARNING"
    ERROR = "ERROR"


class StudentRecordType(StrEnum):
    COURSE_ATTEMPT = "COURSE_ATTEMPT"
    CURRENT_REGISTRATION = "CURRENT_REGISTRATION"
    ACADEMIC_SNAPSHOT = "ACADEMIC_SNAPSHOT"


class DuplicateKind(StrEnum):
    EXACT = "EXACT"
    CONFLICTING = "CONFLICTING"


@dataclass(frozen=True, slots=True)
class StudentStateDiagnostic:
    """A typed finding about input quality or derived-state confidence."""

    code: StudentStateDiagnosticCode
    severity: DiagnosticSeverity
    record_type: StudentRecordType
    reason_codes: tuple[ReasonCode, ...] = ()
    course: CourseIdentity | None = None
    attempt_number: int | None = None
    field: str | None = None
    duplicate_kind: DuplicateKind | None = None
    fatal: bool = False
    requires_human_review: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.code, StudentStateDiagnosticCode):
            raise TypeError("code must be a StudentStateDiagnosticCode")
        if not isinstance(self.severity, DiagnosticSeverity):
            raise TypeError("severity must be a DiagnosticSeverity")
        if not isinstance(self.record_type, StudentRecordType):
            raise TypeError("record_type must be a StudentRecordType")
        reason_codes = tuple(self.reason_codes)
        if not all(isinstance(reason, ReasonCode) for reason in reason_codes):
            raise TypeError("reason_codes must contain only ReasonCode values")
        if self.course is not None and not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity or None")
        if self.attempt_number is not None and (
            isinstance(self.attempt_number, bool)
            or not isinstance(self.attempt_number, int)
            or self.attempt_number < 1
        ):
            raise ValueError("attempt_number must be a positive integer when provided")
        if self.field is not None and (
            not isinstance(self.field, str) or not self.field.strip()
        ):
            raise ValueError("field must be a non-empty string when provided")
        if self.duplicate_kind is not None and not isinstance(
            self.duplicate_kind, DuplicateKind
        ):
            raise TypeError("duplicate_kind must be a DuplicateKind or None")
        if not isinstance(self.fatal, bool):
            raise TypeError("fatal must be a bool")
        if not isinstance(self.requires_human_review, bool):
            raise TypeError("requires_human_review must be a bool")
        object.__setattr__(self, "reason_codes", reason_codes)

    def to_dict(self) -> dict[str, object]:
        """Serialize diagnostics without adding human-language explanations."""

        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "record_type": self.record_type.value,
            "reason_codes": [reason.value for reason in self.reason_codes],
            "course": str(self.course) if self.course is not None else None,
            "attempt_number": self.attempt_number,
            "field": self.field,
            "duplicate_kind": (
                self.duplicate_kind.value if self.duplicate_kind is not None else None
            ),
            "fatal": self.fatal,
            "requires_human_review": self.requires_human_review,
        }


@dataclass(frozen=True, slots=True)
class StudentStateBuildResult:
    """Canonical state plus structured input-quality diagnostics."""

    student_state: StudentState | None
    diagnostics: tuple[StudentStateDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if self.student_state is not None and not isinstance(
            self.student_state, StudentState
        ):
            raise TypeError("student_state must be a StudentState or None")
        diagnostics = tuple(self.diagnostics)
        if not all(
            isinstance(diagnostic, StudentStateDiagnostic) for diagnostic in diagnostics
        ):
            raise TypeError(
                "diagnostics must contain only StudentStateDiagnostic values"
            )
        if self.student_state is not None and any(
            diagnostic.fatal for diagnostic in diagnostics
        ):
            raise ValueError("fatal diagnostics require student_state to be None")
        object.__setattr__(self, "diagnostics", diagnostics)

    @property
    def warnings(self) -> tuple[StudentStateDiagnostic, ...]:
        return tuple(
            diagnostic
            for diagnostic in self.diagnostics
            if diagnostic.severity is DiagnosticSeverity.WARNING
        )

    @property
    def requires_human_review(self) -> bool:
        return any(diagnostic.requires_human_review for diagnostic in self.diagnostics)
