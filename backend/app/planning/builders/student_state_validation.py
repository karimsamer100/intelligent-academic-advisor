"""Validation and deterministic ordering for student-state source records."""

from __future__ import annotations

from collections import defaultdict

from ..domain.course import CourseIdentity, Program, Regulation
from ..domain.reasons import ReasonCode
from ..domain.student_diagnostics import (
    DiagnosticSeverity,
    DuplicateKind,
    StudentRecordType,
    StudentStateDiagnostic,
    StudentStateDiagnosticCode,
)
from ..domain.student_history import (
    AcademicSnapshot,
    AttemptOutcome,
    AttemptPurpose,
    CourseAttempt,
    CurrentRegistration,
)


def validate_records(
    *,
    student_id: str,
    regulation: Regulation,
    program: Program,
    track: str | None,
    attempts: tuple[CourseAttempt, ...],
    registrations: tuple[CurrentRegistration, ...],
    snapshot: AcademicSnapshot | None,
) -> tuple[StudentStateDiagnostic, ...]:
    """Return fatal integrity diagnostics for already-typed source records."""

    diagnostics = [
        *_scope_diagnostics(
            student_id,
            regulation,
            program,
            track,
            attempts,
            registrations,
            snapshot,
        ),
        *_duplicate_diagnostics(attempts, registrations),
        *_contradiction_diagnostics(attempts),
    ]
    return tuple(sort_diagnostics(diagnostics))


def sort_diagnostics(
    diagnostics: list[StudentStateDiagnostic],
) -> list[StudentStateDiagnostic]:
    """Sort diagnostics independently of source collection order."""

    return sorted(
        diagnostics,
        key=lambda diagnostic: (
            diagnostic.record_type.value,
            str(diagnostic.course) if diagnostic.course is not None else "",
            diagnostic.attempt_number or 0,
            diagnostic.code.value,
            diagnostic.field or "",
        ),
    )


def _scope_diagnostics(
    student_id: str,
    regulation: Regulation,
    program: Program,
    track: str | None,
    attempts: tuple[CourseAttempt, ...],
    registrations: tuple[CurrentRegistration, ...],
    snapshot: AcademicSnapshot | None,
) -> tuple[StudentStateDiagnostic, ...]:
    diagnostics: list[StudentStateDiagnostic] = []
    for attempt in attempts:
        reasons = _scope_reasons(
            student_id,
            regulation,
            program,
            attempt.student_id,
            attempt.course.regulation,
            attempt.course.program,
        )
        if reasons:
            diagnostics.append(
                _scope_mismatch(
                    StudentRecordType.COURSE_ATTEMPT,
                    course=attempt.course,
                    attempt_number=attempt.attempt_number,
                    reason_codes=reasons,
                )
            )
    for registration in registrations:
        reasons = _scope_reasons(
            student_id,
            regulation,
            program,
            registration.student_id,
            registration.course.regulation,
            registration.course.program,
        )
        if reasons:
            diagnostics.append(
                _scope_mismatch(
                    StudentRecordType.CURRENT_REGISTRATION,
                    course=registration.course,
                    reason_codes=reasons,
                )
            )
    if snapshot is not None:
        reasons = _scope_reasons(
            student_id,
            regulation,
            program,
            snapshot.student_id,
            snapshot.regulation,
            snapshot.program,
        )
        if track is not None and snapshot.track not in (None, track):
            reasons = (*reasons, ReasonCode.UNSUPPORTED_CASE)
        if reasons:
            diagnostics.append(
                _scope_mismatch(
                    StudentRecordType.ACADEMIC_SNAPSHOT,
                    reason_codes=_unique_reasons(reasons),
                )
            )
    return tuple(diagnostics)


def _scope_reasons(
    expected_student_id: str,
    expected_regulation: Regulation,
    expected_program: Program,
    actual_student_id: str,
    actual_regulation: Regulation,
    actual_program: Program,
) -> tuple[ReasonCode, ...]:
    reasons: list[ReasonCode] = []
    if actual_student_id != expected_student_id:
        reasons.append(ReasonCode.UNSUPPORTED_CASE)
    if actual_regulation is not expected_regulation:
        reasons.append(ReasonCode.WRONG_REGULATION)
    if actual_program != expected_program:
        reasons.append(ReasonCode.WRONG_PROGRAM)
    return tuple(reasons)


def _scope_mismatch(
    record_type: StudentRecordType,
    *,
    course: CourseIdentity | None = None,
    attempt_number: int | None = None,
    reason_codes: tuple[ReasonCode, ...],
) -> StudentStateDiagnostic:
    return StudentStateDiagnostic(
        code=StudentStateDiagnosticCode.SCOPE_MISMATCH,
        severity=DiagnosticSeverity.ERROR,
        record_type=record_type,
        reason_codes=reason_codes,
        course=course,
        attempt_number=attempt_number,
        fatal=True,
        requires_human_review=True,
    )


def _duplicate_diagnostics(
    attempts: tuple[CourseAttempt, ...],
    registrations: tuple[CurrentRegistration, ...],
) -> tuple[StudentStateDiagnostic, ...]:
    diagnostics: list[StudentStateDiagnostic] = []
    attempt_groups: dict[tuple[str, str, int], list[CourseAttempt]] = defaultdict(list)
    for attempt in attempts:
        attempt_groups[
            (attempt.student_id, attempt.course.course_id, attempt.attempt_number)
        ].append(attempt)
    for records in attempt_groups.values():
        if len(records) > 1:
            diagnostics.append(
                _duplicate_diagnostic(
                    StudentRecordType.COURSE_ATTEMPT,
                    course=records[0].course,
                    attempt_number=records[0].attempt_number,
                    duplicate_kind=(
                        DuplicateKind.EXACT
                        if all(record == records[0] for record in records)
                        else DuplicateKind.CONFLICTING
                    ),
                )
            )

    registration_groups: dict[tuple[str, str, str, int], list[CurrentRegistration]] = (
        defaultdict(list)
    )
    for registration in registrations:
        registration_groups[
            (
                registration.student_id,
                registration.course.course_id,
                registration.term,
                registration.academic_year,
            )
        ].append(registration)
    for records in registration_groups.values():
        if len(records) > 1:
            diagnostics.append(
                _duplicate_diagnostic(
                    StudentRecordType.CURRENT_REGISTRATION,
                    course=records[0].course,
                    duplicate_kind=(
                        DuplicateKind.EXACT
                        if all(record == records[0] for record in records)
                        else DuplicateKind.CONFLICTING
                    ),
                )
            )
    return tuple(diagnostics)


def _duplicate_diagnostic(
    record_type: StudentRecordType,
    *,
    course: CourseIdentity,
    duplicate_kind: DuplicateKind,
    attempt_number: int | None = None,
) -> StudentStateDiagnostic:
    return StudentStateDiagnostic(
        code=StudentStateDiagnosticCode.DUPLICATE_RECORD,
        severity=DiagnosticSeverity.ERROR,
        record_type=record_type,
        course=course,
        attempt_number=attempt_number,
        duplicate_kind=duplicate_kind,
        fatal=True,
        requires_human_review=True,
    )


def _contradiction_diagnostics(
    attempts: tuple[CourseAttempt, ...],
) -> tuple[StudentStateDiagnostic, ...]:
    diagnostics: list[StudentStateDiagnostic] = []
    for attempt in attempts:
        terminal_flags = tuple(
            field_name
            for field_name in ("passed", "failed", "withdrawn")
            if getattr(attempt, field_name) is True
        )
        if len(terminal_flags) > 1:
            diagnostics.append(
                StudentStateDiagnostic(
                    code=StudentStateDiagnosticCode.CONTRADICTORY_RECORD,
                    severity=DiagnosticSeverity.ERROR,
                    record_type=StudentRecordType.COURSE_ATTEMPT,
                    course=attempt.course,
                    attempt_number=attempt.attempt_number,
                    field="outcome_flags",
                    fatal=True,
                    requires_human_review=True,
                )
            )
        elif len(terminal_flags) == 1:
            expected_outcome = {
                "passed": AttemptOutcome.PASSED,
                "failed": AttemptOutcome.FAILED,
                "withdrawn": AttemptOutcome.WITHDRAWN,
            }[terminal_flags[0]]
            if attempt.outcome is not expected_outcome:
                diagnostics.append(
                    StudentStateDiagnostic(
                        code=StudentStateDiagnosticCode.CONTRADICTORY_RECORD,
                        severity=DiagnosticSeverity.ERROR,
                        record_type=StudentRecordType.COURSE_ATTEMPT,
                        course=attempt.course,
                        attempt_number=attempt.attempt_number,
                        field="outcome",
                        fatal=True,
                        requires_human_review=True,
                    )
                )
        if attempt.purpose in (AttemptPurpose.REPEAT, AttemptPurpose.IMPROVEMENT) and (
            attempt.repeated is False
        ):
            diagnostics.append(
                StudentStateDiagnostic(
                    code=StudentStateDiagnosticCode.CONTRADICTORY_RECORD,
                    severity=DiagnosticSeverity.ERROR,
                    record_type=StudentRecordType.COURSE_ATTEMPT,
                    course=attempt.course,
                    attempt_number=attempt.attempt_number,
                    field="repeated",
                    fatal=True,
                    requires_human_review=True,
                )
            )
        if attempt.purpose is AttemptPurpose.INITIAL and attempt.repeated is True:
            diagnostics.append(
                StudentStateDiagnostic(
                    code=StudentStateDiagnosticCode.CONTRADICTORY_RECORD,
                    severity=DiagnosticSeverity.ERROR,
                    record_type=StudentRecordType.COURSE_ATTEMPT,
                    course=attempt.course,
                    attempt_number=attempt.attempt_number,
                    field="purpose",
                    fatal=True,
                    requires_human_review=True,
                )
            )
        if attempt.withdrawn is True and (attempt.credits_earned or 0) > 0:
            diagnostics.append(
                StudentStateDiagnostic(
                    code=StudentStateDiagnosticCode.CONTRADICTORY_RECORD,
                    severity=DiagnosticSeverity.ERROR,
                    record_type=StudentRecordType.COURSE_ATTEMPT,
                    course=attempt.course,
                    attempt_number=attempt.attempt_number,
                    field="credits_earned",
                    fatal=True,
                    requires_human_review=True,
                )
            )
    return tuple(diagnostics)


def _unique_reasons(reasons: tuple[ReasonCode, ...]) -> tuple[ReasonCode, ...]:
    return tuple(dict.fromkeys(reasons))
