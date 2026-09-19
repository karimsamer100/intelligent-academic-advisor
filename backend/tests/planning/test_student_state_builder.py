from __future__ import annotations

import inspect

from backend.app.planning.domain.course import CourseIdentity, Program, Regulation
from backend.app.planning.domain.student_diagnostics import (
    DiagnosticSeverity,
    DuplicateKind,
    StudentRecordType,
    StudentStateDiagnosticCode,
)
from backend.app.planning.domain.reasons import ReasonCode
from backend.app.planning.domain.student_history import (
    AcademicSnapshot,
    CourseAttempt,
    CurrentRegistration,
)
from backend.app.planning.domain.student import (
    AcademicHistoryCoverage,
    RegistrationCoverage,
)
from backend.app.planning.builders.student_state_builder import (
    StudentStateBuildInput,
    StudentStateBuilder,
)


def _course(code: str) -> CourseIdentity:
    return CourseIdentity.parse(f"R23:CAIE:{code}")


def _attempt(
    course: CourseIdentity,
    *,
    student_id: str = "student-001",
    attempt_number: int = 1,
    term: str = "Fall",
    academic_year: int = 2024,
    status: str = "recorded",
    passed: bool | None = None,
    failed: bool | None = None,
    withdrawn: bool | None = None,
    repeated: bool | None = None,
    credits_earned: int | float | None = None,
) -> CourseAttempt:
    return CourseAttempt(
        student_id=student_id,
        course=course,
        attempt_number=attempt_number,
        term=term,
        academic_year=academic_year,
        status=status,
        passed=passed,
        failed=failed,
        withdrawn=withdrawn,
        repeated=repeated,
        credits_earned=credits_earned,
    )


def _build(
    *attempts: CourseAttempt,
    current_registrations: tuple[CurrentRegistration, ...] = (),
    academic_snapshot: AcademicSnapshot | None = None,
    track: str | None = None,
    regulation: Regulation = Regulation.R23,
    program: Program | None = None,
):
    selected_program = program or Program("CAIE")
    return StudentStateBuilder().build(
        StudentStateBuildInput(
            student_id="student-001",
            regulation=regulation,
            program=selected_program,
            track=track,
            course_attempts=attempts,
            current_registrations=current_registrations,
            academic_snapshot=academic_snapshot,
            history_coverage=AcademicHistoryCoverage.COMPLETE,
            registration_coverage=RegistrationCoverage.COMPLETE,
        )
    )


def test_builder_can_build_an_empty_complete_history() -> None:
    result = StudentStateBuilder().build(
        StudentStateBuildInput(
            student_id="student-001",
            regulation=Regulation.R23,
            program=Program("CAIE"),
            history_coverage=AcademicHistoryCoverage.COMPLETE,
            registration_coverage=RegistrationCoverage.COMPLETE,
        )
    )

    assert result.student_state is not None
    assert result.student_state.student_id == "student-001"
    assert result.student_state.earned_credit_hours == 0
    assert result.diagnostics == ()


def test_one_explicit_pass_derives_passed_and_completed_course_facts() -> None:
    course = _course("CSE111")

    result = _build(_attempt(course, passed=True, failed=False, credits_earned=3))

    assert result.student_state is not None
    assert result.student_state.passed_courses == frozenset({course})
    assert result.student_state.completed_courses == frozenset({course})
    assert result.student_state.failed_courses == frozenset()
    assert result.student_state.withdrawn_courses == frozenset()
    assert result.student_state.course_attempts == (
        _attempt(course, passed=True, failed=False, credits_earned=3),
    )


def test_explicit_failed_attempt_is_not_passed_or_completed() -> None:
    course = _course("CSE111")

    result = _build(_attempt(course, passed=False, failed=True, credits_earned=0))

    assert result.student_state is not None
    assert result.student_state.passed_courses == frozenset()
    assert result.student_state.completed_courses == frozenset()
    assert result.student_state.failed_courses == frozenset({course})
    assert result.student_state.unknown_pass_status_courses == frozenset()


def test_failed_then_passed_repeat_preserves_history_and_counts_course_once() -> None:
    course = _course("CSE111")
    failed = _attempt(
        course,
        passed=False,
        failed=True,
        credits_earned=0,
    )
    passed = _attempt(
        course,
        attempt_number=2,
        term="Spring",
        passed=True,
        failed=False,
        repeated=True,
        credits_earned=3,
    )

    result = _build(passed, failed)

    assert result.student_state is not None
    assert result.student_state.course_attempts == (failed, passed)
    assert result.student_state.passed_courses == frozenset({course})
    assert result.student_state.completed_courses == frozenset({course})
    assert result.student_state.failed_courses == frozenset({course})
    assert result.student_state.repeated_courses == frozenset({course})
    assert result.student_state.earned_credit_hours == 3


def test_multiple_failed_attempts_preserve_each_attempt_without_earned_credits() -> (
    None
):
    course = _course("CSE111")
    first = _attempt(course, passed=False, failed=True, credits_earned=0)
    second = _attempt(
        course,
        attempt_number=2,
        term="Spring",
        passed=False,
        failed=True,
        repeated=True,
        credits_earned=0,
    )

    result = _build(second, first)

    assert result.student_state is not None
    assert result.student_state.course_attempts == (first, second)
    assert result.student_state.failed_courses == frozenset({course})
    assert result.student_state.repeated_courses == frozenset({course})
    assert result.student_state.earned_credit_hours == 0


def test_withdrawn_attempt_is_preserved_and_not_completed() -> None:
    course = _course("CSE111")

    result = _build(
        _attempt(
            course,
            passed=False,
            withdrawn=True,
            credits_earned=0,
        )
    )

    assert result.student_state is not None
    assert result.student_state.withdrawn_courses == frozenset({course})
    assert result.student_state.passed_courses == frozenset()
    assert result.student_state.completed_courses == frozenset()


def test_current_registration_is_preserved_even_when_course_was_passed() -> None:
    course = _course("CSE111")
    registration = CurrentRegistration(
        student_id="student-001",
        course=course,
        term="Fall",
        academic_year=2025,
        registration_status="registered",
    )

    result = _build(
        _attempt(course, passed=True, failed=False, credits_earned=3),
        current_registrations=(registration,),
    )

    assert result.student_state is not None
    assert result.student_state.current_registrations == (registration,)
    assert result.student_state.current_courses == frozenset({course})
    assert result.student_state.passed_courses == frozenset({course})


def test_equivalent_input_order_produces_equal_deterministic_state() -> None:
    first = _attempt(_course("CSE241"), passed=True, failed=False, credits_earned=3)
    second = _attempt(_course("CSE111"), passed=True, failed=False, credits_earned=3)
    registration_one = CurrentRegistration(
        student_id="student-001",
        course=_course("CSE241"),
        term="Fall",
        academic_year=2025,
    )
    registration_two = CurrentRegistration(
        student_id="student-001",
        course=_course("CSE111"),
        term="Fall",
        academic_year=2025,
    )

    left = _build(
        first,
        second,
        current_registrations=(registration_one, registration_two),
    )
    right = _build(
        second,
        first,
        current_registrations=(registration_two, registration_one),
    )

    assert left == right
    assert left.student_state is not None
    assert [
        attempt.course.course_id for attempt in left.student_state.course_attempts
    ] == [
        "R23:CAIE:CSE111",
        "R23:CAIE:CSE241",
    ]


def test_missing_pass_fact_is_unknown_only_for_its_course() -> None:
    known_course = _course("CSE111")
    unknown_course = _course("CSE999")

    result = _build(
        _attempt(known_course, passed=True, failed=False, credits_earned=3),
        _attempt(unknown_course),
    )

    assert result.student_state is not None
    assert result.student_state.passed_courses == frozenset({known_course})
    assert result.student_state.completed_courses == frozenset({known_course})
    assert result.student_state.unknown_pass_status_courses == frozenset(
        {unknown_course}
    )
    assert result.student_state.unknown_completion_status_courses == frozenset(
        {unknown_course}
    )
    assert any(
        diagnostic.code is StudentStateDiagnosticCode.INCOMPLETE_RECORD
        and diagnostic.course == unknown_course
        and diagnostic.field == "passed"
        for diagnostic in result.diagnostics
    )


def test_builder_does_not_infer_passed_from_grade_status_or_credits() -> None:
    course = _course("CSE111")

    result = _build(
        CourseAttempt(
            student_id="student-001",
            course=course,
            attempt_number=1,
            term="Fall",
            academic_year=2024,
            status="passed",
            grade="A",
            credits_earned=3,
        )
    )

    assert result.student_state is not None
    assert result.student_state.passed_courses == frozenset()
    assert result.student_state.completed_courses == frozenset()
    assert result.student_state.unknown_pass_status_courses == frozenset({course})
    assert any(
        diagnostic.code is StudentStateDiagnosticCode.CREDIT_DATA_CONFLICT
        for diagnostic in result.diagnostics
    )


def test_builder_has_a_typed_pure_input_boundary_without_repository_access() -> None:
    parameters = tuple(inspect.signature(StudentStateBuilder.build).parameters)

    assert parameters == ("self", "input_data")


def test_snapshot_track_conflict_is_fatal_instead_of_being_normalized() -> None:
    snapshot = AcademicSnapshot(
        student_id="student-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        gpa=2.75,
        earned_credit_hours=54,
        track="AI",
    )

    result = _build(academic_snapshot=snapshot, track="SE")

    assert result.student_state is None
    assert result.diagnostics[0].code is StudentStateDiagnosticCode.SCOPE_MISMATCH
    assert result.diagnostics[0].fatal is True


def test_course_regulation_scope_mismatch_is_fatal_and_requires_review() -> None:
    foreign_course = CourseIdentity.parse("R18:CAIE:CSE111")

    result = _build(_attempt(foreign_course, passed=True, credits_earned=3))

    assert result.student_state is None
    assert result.requires_human_review is True
    diagnostic = result.diagnostics[0]
    assert diagnostic.code is StudentStateDiagnosticCode.SCOPE_MISMATCH
    assert diagnostic.record_type is StudentRecordType.COURSE_ATTEMPT
    assert diagnostic.reason_codes == (ReasonCode.WRONG_REGULATION,)
    assert diagnostic.fatal is True
    assert diagnostic.severity is DiagnosticSeverity.ERROR


def test_course_program_scope_mismatch_is_fatal_and_requires_review() -> None:
    foreign_course = CourseIdentity.parse("R23:CESS:CSE111")

    result = _build(_attempt(foreign_course, passed=True, credits_earned=3))

    assert result.student_state is None
    diagnostic = result.diagnostics[0]
    assert diagnostic.code is StudentStateDiagnosticCode.SCOPE_MISMATCH
    assert diagnostic.reason_codes == (ReasonCode.WRONG_PROGRAM,)


def test_student_id_scope_mismatch_is_fatal() -> None:
    result = _build(
        _attempt(
            _course("CSE111"),
            student_id="different-student",
            passed=True,
            credits_earned=3,
        )
    )

    assert result.student_state is None
    assert result.diagnostics[0].code is StudentStateDiagnosticCode.SCOPE_MISMATCH
    assert result.diagnostics[0].fatal is True


def test_contradictory_attempt_flags_are_fatal() -> None:
    result = _build(
        _attempt(
            _course("CSE111"),
            passed=True,
            failed=True,
            credits_earned=3,
        )
    )

    assert result.student_state is None
    assert result.diagnostics[0].code is StudentStateDiagnosticCode.CONTRADICTORY_RECORD
    assert result.diagnostics[0].record_type is StudentRecordType.COURSE_ATTEMPT
    assert result.diagnostics[0].fatal is True
    assert result.requires_human_review is True


def test_withdrawn_attempt_with_positive_earned_credits_is_fatal() -> None:
    result = _build(
        _attempt(
            _course("CSE111"),
            passed=False,
            withdrawn=True,
            credits_earned=3,
        )
    )

    assert result.student_state is None
    assert result.diagnostics[0].code is StudentStateDiagnosticCode.CONTRADICTORY_RECORD
    assert result.diagnostics[0].field == "credits_earned"


def test_exact_duplicate_attempt_is_reported_and_not_silently_deduplicated() -> None:
    attempt = _attempt(_course("CSE111"), passed=True, credits_earned=3)

    result = _build(attempt, attempt)

    assert result.student_state is None
    diagnostic = result.diagnostics[0]
    assert diagnostic.code is StudentStateDiagnosticCode.DUPLICATE_RECORD
    assert diagnostic.duplicate_kind is DuplicateKind.EXACT
    assert diagnostic.fatal is True


def test_conflicting_duplicate_attempt_identity_is_fatal() -> None:
    first = _attempt(_course("CSE111"), passed=True, credits_earned=3)
    second = _attempt(
        _course("CSE111"),
        term="Spring",
        passed=False,
        failed=True,
        credits_earned=0,
    )

    result = _build(first, second)

    assert result.student_state is None
    diagnostic = result.diagnostics[0]
    assert diagnostic.code is StudentStateDiagnosticCode.DUPLICATE_RECORD
    assert diagnostic.duplicate_kind is DuplicateKind.CONFLICTING
    assert diagnostic.fatal is True


def test_duplicate_current_registration_is_reported_as_fatal() -> None:
    registration = CurrentRegistration(
        student_id="student-001",
        course=_course("CSE111"),
        term="Fall",
        academic_year=2025,
    )

    result = _build(current_registrations=(registration, registration))

    assert result.student_state is None
    assert result.diagnostics[0].record_type is StudentRecordType.CURRENT_REGISTRATION
    assert result.diagnostics[0].duplicate_kind is DuplicateKind.EXACT


def test_snapshot_facts_override_derived_credits_and_are_passed_through() -> None:
    snapshot = AcademicSnapshot(
        student_id="student-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        gpa=2.75,
        earned_credit_hours=54,
        registered_credit_hours=12,
        academic_level="junior",
        academic_standing="good",
        track="AI",
    )

    result = _build(
        _attempt(_course("CSE111"), passed=True, credits_earned=3),
        academic_snapshot=snapshot,
    )

    assert result.student_state is not None
    assert result.student_state.earned_credit_hours == 54
    assert result.student_state.gpa == 2.75
    assert result.student_state.registered_credit_hours == 12
    assert result.student_state.academic_level == "junior"
    assert result.student_state.academic_standing == "good"
    assert result.student_state.track == "AI"


def test_snapshot_and_derived_credit_disagreement_keeps_snapshot_and_requires_review() -> (
    None
):
    snapshot = AcademicSnapshot(
        student_id="student-001",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        gpa=2.75,
        earned_credit_hours=54,
    )

    result = _build(
        _attempt(_course("CSE111"), passed=True, credits_earned=3),
        academic_snapshot=snapshot,
    )

    assert result.student_state is not None
    assert result.student_state.earned_credit_hours == 54
    assert any(
        diagnostic.code is StudentStateDiagnosticCode.CREDIT_DATA_CONFLICT
        for diagnostic in result.diagnostics
    )
    assert result.requires_human_review is True


def test_missing_passed_attempt_credit_keeps_state_but_makes_derived_total_unknown() -> (
    None
):
    result = _build(_attempt(_course("CSE111"), passed=True, credits_earned=None))

    assert result.student_state is not None
    assert result.student_state.passed_courses == frozenset({_course("CSE111")})
    assert result.student_state.earned_credit_hours is None
    assert any(
        diagnostic.code is StudentStateDiagnosticCode.INCOMPLETE_RECORD
        and diagnostic.field == "credits_earned"
        for diagnostic in result.diagnostics
    )
    assert result.requires_human_review is True


def test_conflicting_passed_attempt_credit_values_require_review() -> None:
    course = _course("CSE111")
    first = _attempt(course, passed=True, credits_earned=3)
    second = _attempt(course, attempt_number=2, passed=True, credits_earned=4)

    result = _build(first, second)

    assert result.student_state is not None
    assert result.student_state.passed_courses == frozenset({course})
    assert result.student_state.earned_credit_hours is None
    assert any(
        diagnostic.code is StudentStateDiagnosticCode.CREDIT_DATA_CONFLICT
        and diagnostic.course == course
        for diagnostic in result.diagnostics
    )
    assert result.requires_human_review is True


def test_missing_snapshot_keeps_gpa_optional_and_does_not_calculate_it() -> None:
    result = _build()

    assert result.student_state is not None
    assert result.student_state.gpa is None


def test_snapshot_scope_mismatch_is_fatal() -> None:
    snapshot = AcademicSnapshot(
        student_id="student-001",
        regulation=Regulation.R18,
        program=Program("CAIE"),
        gpa=2.75,
        earned_credit_hours=54,
    )

    result = _build(academic_snapshot=snapshot)

    assert result.student_state is None
    assert result.diagnostics[0].record_type is StudentRecordType.ACADEMIC_SNAPSHOT
    assert result.diagnostics[0].reason_codes == (ReasonCode.WRONG_REGULATION,)
