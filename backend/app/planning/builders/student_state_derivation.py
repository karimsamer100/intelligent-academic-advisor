"""Pure per-course and aggregate fact derivation for student state."""

from __future__ import annotations

from ..domain.academic_state import (
    AcademicHistoryCoverage,
    CourseAcademicRecord,
    EffectiveCourseStatus,
    FactStatus,
    RegistrationCoverage,
)
from ..domain.course import CourseIdentity
from ..domain.reasons import ReasonCode
from ..domain.student_diagnostics import (
    DiagnosticSeverity,
    StudentRecordType,
    StudentStateDiagnostic,
    StudentStateDiagnosticCode,
)
from ..domain.student_history import (
    AttemptOutcome,
    AttemptPurpose,
    CourseAttempt,
    CurrentRegistration,
)


def build_course_records(
    *,
    attempts: tuple[CourseAttempt, ...],
    registrations: tuple[CurrentRegistration, ...],
    history_coverage: AcademicHistoryCoverage | None,
    registration_coverage: RegistrationCoverage | None,
) -> tuple[CourseAcademicRecord, ...]:
    """Build deterministic immutable records without applying regulation rules."""

    attempts_by_course: dict[CourseIdentity, list[CourseAttempt]] = {}
    registrations_by_course: dict[CourseIdentity, list[CurrentRegistration]] = {}
    for attempt in attempts:
        attempts_by_course.setdefault(attempt.course, []).append(attempt)
    for registration in registrations:
        registrations_by_course.setdefault(registration.course, []).append(registration)

    courses = sorted(
        set(attempts_by_course) | set(registrations_by_course),
        key=str,
    )
    records: list[CourseAcademicRecord] = []
    for course in courses:
        course_attempts = tuple(attempts_by_course.get(course, ()))
        course_registrations = tuple(registrations_by_course.get(course, ()))
        registration_status = _registration_fact(
            bool(course_registrations), registration_coverage
        )
        pass_status, effective_status, state_diagnostics = _derive_effective_state(
            course_attempts,
            history_coverage,
            registration_status,
        )
        earned_credits, credit_diagnostics = _derive_course_credits(
            course_attempts,
            pass_status,
        )
        records.append(
            CourseAcademicRecord(
                course=course,
                attempts=course_attempts,
                current_registrations=course_registrations,
                effective_status=effective_status,
                pass_status=pass_status,
                registration_status=registration_status,
                earned_credits=earned_credits,
                diagnostics=(*state_diagnostics, *credit_diagnostics),
            )
        )
    return tuple(records)


def derive_total_credits(
    records: tuple[CourseAcademicRecord, ...],
    *,
    history_coverage: AcademicHistoryCoverage | None,
) -> int | float | None:
    """Derive distinct successful-course credits only from complete facts."""

    if history_coverage is not AcademicHistoryCoverage.COMPLETE:
        return None
    total: int | float = 0
    for record in records:
        if record.pass_status is FactStatus.UNKNOWN:
            return None
        if record.pass_status is FactStatus.KNOWN_TRUE:
            if record.earned_credits is None:
                return None
            total += record.earned_credits
    return total


def _registration_fact(
    has_registration: bool,
    coverage: RegistrationCoverage | None,
) -> FactStatus:
    if has_registration:
        return FactStatus.KNOWN_TRUE
    if coverage is RegistrationCoverage.COMPLETE:
        return FactStatus.KNOWN_FALSE
    return FactStatus.UNKNOWN


def _derive_effective_state(
    attempts: tuple[CourseAttempt, ...],
    coverage: AcademicHistoryCoverage | None,
    registration_status: FactStatus,
) -> tuple[FactStatus, EffectiveCourseStatus, tuple[StudentStateDiagnostic, ...]]:
    diagnostics: list[StudentStateDiagnostic] = []
    if not attempts:
        pass_status = (
            FactStatus.KNOWN_FALSE
            if coverage is AcademicHistoryCoverage.COMPLETE
            else FactStatus.UNKNOWN
        )
        return (
            pass_status,
            _effective_from_pass_and_registration(pass_status, registration_status),
            (),
        )

    if any(attempt.outcome is AttemptOutcome.UNKNOWN for attempt in attempts):
        diagnostics.extend(
            _unknown_outcome_diagnostic(attempt)
            for attempt in attempts
            if attempt.outcome is AttemptOutcome.UNKNOWN
        )
        return (
            FactStatus.UNKNOWN,
            _effective_from_pass_and_registration(
                FactStatus.UNKNOWN,
                registration_status,
            ),
            tuple(diagnostics),
        )

    passed_positions = [
        index
        for index, attempt in enumerate(attempts)
        if attempt.outcome is AttemptOutcome.PASSED
    ]
    if passed_positions:
        first_pass = passed_positions[0]
        later_attempts = attempts[first_pass + 1 :]
        if not later_attempts:
            pass_status = FactStatus.KNOWN_TRUE
        else:
            latest = later_attempts[-1]
            if latest.purpose is AttemptPurpose.IMPROVEMENT:
                if latest.outcome is AttemptOutcome.PASSED:
                    pass_status = FactStatus.KNOWN_TRUE
                elif latest.outcome is AttemptOutcome.FAILED:
                    pass_status = FactStatus.KNOWN_FALSE
                else:
                    pass_status = FactStatus.UNKNOWN
            elif all(
                attempt.outcome is AttemptOutcome.PASSED for attempt in later_attempts
            ):
                pass_status = FactStatus.KNOWN_TRUE
            else:
                pass_status = FactStatus.UNKNOWN
                diagnostics.extend(
                    _repeat_uncertainty_diagnostic(attempt)
                    for attempt in later_attempts
                    if attempt.purpose
                    not in (
                        AttemptPurpose.INITIAL,
                        AttemptPurpose.REPEAT,
                        AttemptPurpose.IMPROVEMENT,
                    )
                    or attempt.outcome is not AttemptOutcome.PASSED
                )
    elif coverage is AcademicHistoryCoverage.COMPLETE:
        pass_status = FactStatus.KNOWN_FALSE
    else:
        pass_status = FactStatus.UNKNOWN
        diagnostics.append(
            StudentStateDiagnostic(
                code=StudentStateDiagnosticCode.INCOMPLETE_RECORD,
                severity=DiagnosticSeverity.WARNING,
                record_type=StudentRecordType.COURSE_ATTEMPT,
                reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                course=attempts[0].course,
                field="history_coverage",
                requires_human_review=True,
            )
        )

    if (
        coverage is not AcademicHistoryCoverage.COMPLETE
        and pass_status is not FactStatus.UNKNOWN
    ):
        pass_status = FactStatus.UNKNOWN
        diagnostics.append(
            StudentStateDiagnostic(
                code=StudentStateDiagnosticCode.INCOMPLETE_RECORD,
                severity=DiagnosticSeverity.WARNING,
                record_type=StudentRecordType.COURSE_ATTEMPT,
                reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                course=attempts[0].course,
                field="history_coverage",
                requires_human_review=True,
            )
        )

    return (
        pass_status,
        _effective_from_attempts(attempts, pass_status, registration_status),
        tuple(diagnostics),
    )


def _effective_from_pass_and_registration(
    pass_status: FactStatus,
    registration_status: FactStatus,
) -> EffectiveCourseStatus:
    if (
        registration_status is FactStatus.KNOWN_TRUE
        and pass_status is not FactStatus.KNOWN_TRUE
    ):
        return EffectiveCourseStatus.IN_PROGRESS
    if pass_status is FactStatus.KNOWN_TRUE:
        return EffectiveCourseStatus.PASSED
    if registration_status is FactStatus.UNKNOWN:
        return EffectiveCourseStatus.UNKNOWN
    if pass_status is FactStatus.UNKNOWN:
        return EffectiveCourseStatus.UNKNOWN
    return EffectiveCourseStatus.NOT_ATTEMPTED


def _effective_from_attempts(
    attempts: tuple[CourseAttempt, ...],
    pass_status: FactStatus,
    registration_status: FactStatus,
) -> EffectiveCourseStatus:
    if (
        registration_status is FactStatus.KNOWN_TRUE
        and pass_status is not FactStatus.KNOWN_TRUE
    ):
        return EffectiveCourseStatus.IN_PROGRESS
    if pass_status is FactStatus.KNOWN_TRUE:
        return EffectiveCourseStatus.PASSED
    if registration_status is FactStatus.UNKNOWN:
        return EffectiveCourseStatus.UNKNOWN
    if pass_status is FactStatus.UNKNOWN:
        return EffectiveCourseStatus.UNKNOWN
    latest = attempts[-1].outcome
    return {
        AttemptOutcome.FAILED: EffectiveCourseStatus.FAILED,
        AttemptOutcome.WITHDRAWN: EffectiveCourseStatus.WITHDRAWN,
        AttemptOutcome.INCOMPLETE: EffectiveCourseStatus.INCOMPLETE,
    }.get(latest, EffectiveCourseStatus.UNKNOWN)


def _derive_course_credits(
    attempts: tuple[CourseAttempt, ...],
    pass_status: FactStatus,
) -> tuple[int | float | None, tuple[StudentStateDiagnostic, ...]]:
    diagnostics: list[StudentStateDiagnostic] = []
    diagnostics.extend(
        StudentStateDiagnostic(
            code=StudentStateDiagnosticCode.CREDIT_DATA_CONFLICT,
            severity=DiagnosticSeverity.WARNING,
            record_type=StudentRecordType.COURSE_ATTEMPT,
            course=attempt.course,
            attempt_number=attempt.attempt_number,
            field="credits_earned",
            requires_human_review=True,
        )
        for attempt in attempts
        if attempt.outcome is not AttemptOutcome.PASSED
        and attempt.credits_earned is not None
        and attempt.credits_earned > 0
    )
    if pass_status is not FactStatus.KNOWN_TRUE:
        return None, tuple(diagnostics)

    passed_attempts = tuple(
        attempt for attempt in attempts if attempt.outcome is AttemptOutcome.PASSED
    )
    credits = {attempt.credits_earned for attempt in passed_attempts}
    if None in credits:
        diagnostics.extend(
            StudentStateDiagnostic(
                code=StudentStateDiagnosticCode.INCOMPLETE_RECORD,
                severity=DiagnosticSeverity.WARNING,
                record_type=StudentRecordType.COURSE_ATTEMPT,
                reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                course=attempt.course,
                attempt_number=attempt.attempt_number,
                field="credits_earned",
                requires_human_review=True,
            )
            for attempt in passed_attempts
            if attempt.credits_earned is None
        )
        return None, tuple(diagnostics)
    if len(credits) > 1:
        diagnostics.append(
            StudentStateDiagnostic(
                code=StudentStateDiagnosticCode.CREDIT_DATA_CONFLICT,
                severity=DiagnosticSeverity.WARNING,
                record_type=StudentRecordType.COURSE_ATTEMPT,
                course=attempts[0].course,
                field="credits_earned",
                requires_human_review=True,
            )
        )
        return None, tuple(diagnostics)
    return next(iter(credits)), tuple(diagnostics)


def _unknown_outcome_diagnostic(attempt: CourseAttempt) -> StudentStateDiagnostic:
    return StudentStateDiagnostic(
        code=StudentStateDiagnosticCode.INCOMPLETE_RECORD,
        severity=DiagnosticSeverity.WARNING,
        record_type=StudentRecordType.COURSE_ATTEMPT,
        reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
        course=attempt.course,
        attempt_number=attempt.attempt_number,
        field="passed",
        requires_human_review=True,
    )


def _repeat_uncertainty_diagnostic(
    attempt: CourseAttempt,
) -> StudentStateDiagnostic:
    return StudentStateDiagnostic(
        code=StudentStateDiagnosticCode.REPEAT_SEMANTICS_UNRESOLVED,
        severity=DiagnosticSeverity.WARNING,
        record_type=StudentRecordType.COURSE_ATTEMPT,
        reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
        course=attempt.course,
        attempt_number=attempt.attempt_number,
        field="purpose",
        requires_human_review=True,
    )
