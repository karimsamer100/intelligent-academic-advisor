from __future__ import annotations

import pytest

from app.planning.audit.service import DegreeAuditService
from app.planning.domain.audit import (
    DegreeAuditRequest,
    DegreeAuditStatus,
)
from app.planning.domain.academic_state import (
    AcademicHistoryCoverage,
    RegistrationCoverage,
)
from app.planning.domain.course import CourseIdentity, Program, Regulation
from app.planning.domain.electives import (
    Concentration,
    ConcentrationId,
    ElectivePool,
    ElectivePoolId,
    ElectivePoolType,
    ElectiveSlotId,
)
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.program_facts import (
    FieldTrainingRecord,
    ProgramFactCoverage,
    StudentProgramFacts,
)
from app.planning.domain.requirements import (
    ConcentrationRequirement,
    CourseCompletionRequirement,
    CourseCountFromPoolRequirement,
    ElectiveSlotRequirement,
    EarnedCreditThresholdRequirement,
    FieldTrainingRequirement,
    MinimumGPARequirement,
    ProgramRequirement,
    ProgramRequirementSet,
    RequirementSetStatus,
    RequirementStage,
    TotalProgramCreditsRequirement,
    ZeroCreditCourseRequirement,
)
from app.planning.domain.requirements import RequirementDefinition
from app.planning.domain.student import StudentState
from app.planning.domain.version import DatasetVersion
from app.planning.policy import ExecutionPolicy


R23 = Regulation.R23
R18 = Regulation.R18
CAIE = Program("CAIE")
CESS = Program("CESS")
VERSION = DatasetVersion("degree-audit-test")


def course(code: str, *, regulation: Regulation = R23, program: Program = CAIE):
    return CourseIdentity(regulation, program, code)


def requirement(definition, requirement_id: str = "REQ-1", **kwargs):
    return ProgramRequirement(
        requirement_id=requirement_id,
        regulation=R23,
        program=CAIE,
        approval_status=kwargs.pop("approval_status", ApprovalStatus.APPROVED),
        verification_status=kwargs.pop(
            "verification_status", VerificationStatus.SOURCE_VERIFIED
        ),
        definition=definition,
        **kwargs,
    )


def requirement_set(*requirements, status=RequirementSetStatus.COMPLETE):
    return ProgramRequirementSet(
        regulation=R23,
        program=CAIE,
        requirements=tuple(requirements),
        status=status,
        dataset_version=VERSION,
    )


def student(
    *,
    passed=(),
    current=(),
    earned=0,
    gpa=None,
    history=AcademicHistoryCoverage.COMPLETE,
    registration=RegistrationCoverage.COMPLETE,
):
    return StudentState(
        student_id="audit-student",
        regulation=R23,
        program=CAIE,
        passed_courses=frozenset(passed),
        current_courses=frozenset(current),
        earned_credit_hours=earned,
        gpa=gpa,
        history_coverage=history,
        registration_coverage=registration,
    )


def request(
    requirements,
    *,
    student_state=None,
    pools=(),
    concentrations=(),
    facts=None,
    stage=RequirementStage.PROGRAM_COMPLETION,
    status=RequirementSetStatus.COMPLETE,
):
    return DegreeAuditRequest(
        student=student_state or student(),
        requirement_set=requirement_set(*requirements, status=status),
        stage=stage,
        pools=tuple(pools),
        concentrations=tuple(concentrations),
        program_facts=facts or StudentProgramFacts(),
    )


def service(*, authoritative=False):
    return DegreeAuditService(
        policy=(
            ExecutionPolicy.authoritative()
            if authoritative
            else ExecutionPolicy.development()
        ),
        dataset_version=VERSION,
    )


def technical_pool(courses):
    return ElectivePool(
        pool_id=ElectivePoolId(R23, CAIE, "TECHNICAL"),
        pool_name="Technical electives",
        pool_type=ElectivePoolType.PROGRAM_TECHNICAL_ELECTIVES,
        allowed_courses=tuple(courses),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )


def test_passed_required_course_is_satisfied() -> None:
    target = course("CSE341")
    result = service().audit(
        request(
            [requirement(CourseCompletionRequirement(target))],
            student_state=student(passed=(target,)),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    assert result.requirement_results[0].outcome.value == "SATISFIED"


def test_failed_required_course_is_unsatisfied() -> None:
    target = course("CSE341")
    result = service().audit(
        request([requirement(CourseCompletionRequirement(target))])
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_NOT_SATISFIED
    assert result.progress.outstanding_requirement_ids == ("REQ-1",)


def test_unknown_course_history_is_indeterminate() -> None:
    target = course("CSE341")
    result = service().audit(
        request(
            [requirement(CourseCompletionRequirement(target))],
            student_state=student(history=AcademicHistoryCoverage.UNAVAILABLE),
        )
    )

    assert result.status is DegreeAuditStatus.HUMAN_REVIEW_REQUIRED
    assert result.requirement_results[0].outcome.value == "INDETERMINATE"


def test_complete_empty_requirement_set_is_explicitly_satisfied() -> None:
    result = service().audit(request([]))

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    assert result.requirement_results == ()


def test_currently_registered_required_course_is_not_satisfied_but_is_progress() -> (
    None
):
    target = course("CSE341")
    result = service().audit(
        request(
            [requirement(CourseCompletionRequirement(target))],
            student_state=student(current=(target,)),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_NOT_SATISFIED
    assert result.progress.in_progress_requirement_ids == ("REQ-1",)


def test_zero_credit_course_requires_pass_without_adding_credits() -> None:
    target = course("ASUx11")
    result = service().audit(
        request(
            [requirement(ZeroCreditCourseRequirement(target))],
            student_state=student(passed=(target,), earned=0),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    assert result.progress.earned_credit_hours == 0
    assert result.progress.zero_credit_requirements.satisfied_count == 1


@pytest.mark.parametrize(
    ("earned", "expected"),
    [
        (144, DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED),
        (143, DegreeAuditStatus.ACADEMIC_REQUIREMENTS_NOT_SATISFIED),
    ],
)
def test_program_credit_threshold_is_evaluated(earned, expected) -> None:
    result = service().audit(
        request(
            [requirement(TotalProgramCreditsRequirement(144))],
            student_state=student(earned=earned),
        )
    )

    assert result.status is expected


def test_unknown_earned_credits_are_not_treated_as_zero() -> None:
    result = service().audit(
        request(
            [requirement(TotalProgramCreditsRequirement(144))],
            student_state=student(earned=None),
        )
    )

    assert result.status is DegreeAuditStatus.HUMAN_REVIEW_REQUIRED


def test_registration_gate_can_be_audited_only_when_requested_explicitly() -> None:
    gate = requirement(
        EarnedCreditThresholdRequirement(101, RequirementStage.REGISTRATION_GATE),
        "REQ-101",
    )

    result = service().audit(
        request(
            [gate],
            stage=RequirementStage.REGISTRATION_GATE,
            student_state=student(earned=101),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    assert result.progress.required_program_credits is None


def test_gpa_requirement_uses_snapshot_only() -> None:
    definition = MinimumGPARequirement(2.0)
    assert (
        service()
        .audit(request([requirement(definition)], student_state=student(gpa=2.0)))
        .status
        is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    )
    assert (
        service()
        .audit(request([requirement(definition)], student_state=student(gpa=1.9)))
        .status
        is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_NOT_SATISFIED
    )
    assert (
        service()
        .audit(request([requirement(definition)], student_state=student(gpa=None)))
        .status
        is DegreeAuditStatus.HUMAN_REVIEW_REQUIRED
    )


def test_registration_gate_is_excluded_from_program_completion_audit() -> None:
    gate = requirement(
        EarnedCreditThresholdRequirement(101, RequirementStage.REGISTRATION_GATE),
        "REQ-101",
    )
    total = requirement(
        TotalProgramCreditsRequirement(144, RequirementStage.PROGRAM_COMPLETION),
        "REQ-144",
    )
    result = service().audit(request([gate, total], student_state=student(earned=144)))

    assert tuple(item.requirement_id for item in result.requirement_results) == (
        "REQ-144",
    )


def test_incomplete_requirement_set_cannot_claim_success() -> None:
    target = course("CSE341")
    result = service().audit(
        request(
            [requirement(CourseCompletionRequirement(target))],
            student_state=student(passed=(target,)),
            status=RequirementSetStatus.INCOMPLETE,
        )
    )

    assert result.status is DegreeAuditStatus.HUMAN_REVIEW_REQUIRED
    assert result.metadata.authoritative is False


def test_unavailable_requirement_set_cannot_claim_success() -> None:
    result = service().audit(request([], status=RequirementSetStatus.UNAVAILABLE))

    assert result.status is DegreeAuditStatus.HUMAN_REVIEW_REQUIRED


def test_blocked_critical_requirement_prevents_authoritative_success() -> None:
    target = course("CSE341")
    result = service(authoritative=True).audit(
        request(
            [
                requirement(
                    CourseCompletionRequirement(target),
                    approval_status=ApprovalStatus.BLOCKED,
                )
            ],
            student_state=student(passed=(target,)),
        )
    )

    assert result.status is DegreeAuditStatus.HUMAN_REVIEW_REQUIRED
    assert result.metadata.authoritative is False


def test_development_result_is_explicitly_non_authoritative() -> None:
    target = course("CSE341")
    result = service().audit(
        request(
            [requirement(CourseCompletionRequirement(target))],
            student_state=student(passed=(target,)),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    assert result.metadata.authoritative is False


def test_authoritative_safe_complete_audit_is_authoritative() -> None:
    target = course("CSE341")
    result = service(authoritative=True).audit(
        request(
            [requirement(CourseCompletionRequirement(target))],
            student_state=student(passed=(target,)),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    assert result.metadata.authoritative is True


def test_metadata_only_requirement_is_not_silently_ignored() -> None:
    result = service().audit(request([requirement(None)]))

    assert result.status is DegreeAuditStatus.UNSUPPORTED
    assert result.progress.unknown_requirement_ids == ("REQ-1",)


def test_complete_pool_count_counts_each_passed_course_once() -> None:
    candidates = tuple(course(f"CSE{400 + index}") for index in range(7))
    pool = technical_pool(candidates)
    definition = CourseCountFromPoolRequirement(pool.pool_id, 7, 3)
    result = service().audit(
        request(
            [requirement(definition)],
            student_state=student(passed=candidates),
            pools=(pool,),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    evidence = result.requirement_results[0].evidence
    assert evidence.known_passed_count == 7
    assert len(evidence.known_passed_courses) == 7


def test_pool_count_with_unknown_candidates_is_indeterminate_when_needed() -> None:
    candidates = tuple(course(f"CSE{400 + index}") for index in range(8))
    pool = technical_pool(candidates)
    result = service().audit(
        request(
            [requirement(CourseCountFromPoolRequirement(pool.pool_id, 7))],
            student_state=student(
                passed=candidates[:5], history=AcademicHistoryCoverage.UNAVAILABLE
            ),
            pools=(pool,),
        )
    )

    assert result.status is DegreeAuditStatus.HUMAN_REVIEW_REQUIRED
    assert result.requirement_results[0].evidence.unknown_count == 3


def test_pool_count_can_prove_maximum_below_requirement() -> None:
    candidates = tuple(course(f"CSE{400 + index}") for index in range(6))
    pool = technical_pool(candidates)
    result = service().audit(
        request(
            [requirement(CourseCountFromPoolRequirement(pool.pool_id, 7))],
            student_state=student(
                passed=candidates[:4], history=AcademicHistoryCoverage.PARTIAL
            ),
            pools=(pool,),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_NOT_SATISFIED
    assert result.requirement_results[0].evidence.maximum_possible_count == 6


def test_blocked_pool_cannot_drive_authoritative_success() -> None:
    candidate = course("CSE401")
    pool = ElectivePool(
        pool_id=ElectivePoolId(R23, CAIE, "TECHNICAL"),
        pool_name="Blocked technical",
        pool_type=ElectivePoolType.PROGRAM_TECHNICAL_ELECTIVES,
        allowed_courses=(candidate,),
        approval_status=ApprovalStatus.BLOCKED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    result = service(authoritative=True).audit(
        request(
            [requirement(CourseCountFromPoolRequirement(pool.pool_id, 1))],
            student_state=student(passed=(candidate,)),
            pools=(pool,),
        )
    )

    assert result.status is DegreeAuditStatus.HUMAN_REVIEW_REQUIRED
    assert result.metadata.authoritative is False


def test_blocked_concentration_membership_cannot_drive_authoritative_success() -> None:
    candidate = course("CSE501")
    concentration_id = ConcentrationId(R23, CAIE, "DATA_SCIENCE")
    concentration = Concentration(
        concentration_id,
        "Blocked data science",
        (candidate,),
        approval_status=ApprovalStatus.BLOCKED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    result = service(authoritative=True).audit(
        request(
            [
                requirement(
                    ConcentrationRequirement(
                        ElectivePoolId(R23, CAIE, "TECHNICAL"),
                        1,
                        (concentration_id,),
                    )
                )
            ],
            student_state=student(passed=(candidate,)),
            concentrations=(concentration,),
        )
    )

    assert result.status is DegreeAuditStatus.HUMAN_REVIEW_REQUIRED
    assert result.metadata.authoritative is False


def test_concentration_is_inferred_from_qualifying_courses() -> None:
    candidates = tuple(course(f"CSE{500 + index}") for index in range(5))
    concentration_id = ConcentrationId(R23, CAIE, "DATA_SCIENCE")
    concentration = Concentration(concentration_id, "Data Science", candidates)
    technical_id = ElectivePoolId(R23, CAIE, "TECHNICAL")
    result = service().audit(
        request(
            [
                requirement(
                    ConcentrationRequirement(technical_id, 5, (concentration_id,))
                )
            ],
            student_state=student(passed=candidates),
            concentrations=(concentration,),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    assert result.progress.concentrations[0].known_passed_count == 5


def test_concentration_with_four_of_five_is_unsatisfied_when_complete() -> None:
    candidates = tuple(course(f"CSE{500 + index}") for index in range(5))
    concentration_id = ConcentrationId(R23, CAIE, "DATA_SCIENCE")
    concentration = Concentration(concentration_id, "Data Science", candidates)
    result = service().audit(
        request(
            [
                requirement(
                    ConcentrationRequirement(
                        ElectivePoolId(R23, CAIE, "TECHNICAL"),
                        5,
                        (concentration_id,),
                    )
                )
            ],
            student_state=student(passed=candidates[:4]),
            concentrations=(concentration,),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_NOT_SATISFIED


def test_concentration_unknown_candidate_is_not_assumed_failed() -> None:
    candidates = tuple(course(f"CSE{500 + index}") for index in range(5))
    concentration_id = ConcentrationId(R23, CAIE, "DATA_SCIENCE")
    concentration = Concentration(concentration_id, "Data Science", candidates)
    result = service().audit(
        request(
            [
                requirement(
                    ConcentrationRequirement(
                        ElectivePoolId(R23, CAIE, "TECHNICAL"),
                        5,
                        (concentration_id,),
                    )
                )
            ],
            student_state=student(
                passed=candidates[:4], history=AcademicHistoryCoverage.PARTIAL
            ),
            concentrations=(concentration,),
        )
    )

    assert result.status is DegreeAuditStatus.HUMAN_REVIEW_REQUIRED


def test_elective_slots_use_distinct_courses_deterministically() -> None:
    first = course("CSE601")
    second = course("CSE602")
    pool = ElectivePool(
        pool_id=ElectivePoolId(R23, CAIE, "UNIVERSITY_1"),
        pool_name="University electives",
        pool_type=ElectivePoolType.UNIVERSITY_ELECTIVE,
        allowed_courses=(first, second),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    requirements = [
        requirement(
            ElectiveSlotRequirement(ElectiveSlotId(R23, CAIE, "ASU_1"), pool.pool_id),
            "SLOT-1",
        ),
        requirement(
            ElectiveSlotRequirement(ElectiveSlotId(R23, CAIE, "ASU_2"), pool.pool_id),
            "SLOT-2",
        ),
    ]
    result = service().audit(
        request(
            requirements, student_state=student(passed=(first, second)), pools=(pool,)
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    allocations = [
        item.evidence.allocated_course for item in result.requirement_results
    ]
    assert allocations == sorted(allocations, key=lambda item: item.course_id)
    assert len(set(allocations)) == 2


def test_unknown_slot_pool_binding_is_indeterminate() -> None:
    result = service().audit(
        request(
            [
                requirement(
                    ElectiveSlotRequirement(ElectiveSlotId(R23, CAIE, "ASU_1"), None)
                )
            ]
        )
    )

    assert result.status is DegreeAuditStatus.HUMAN_REVIEW_REQUIRED


def test_two_slots_cannot_consume_the_same_passed_course() -> None:
    candidate = course("CSE601")
    pool = ElectivePool(
        pool_id=ElectivePoolId(R23, CAIE, "UNIVERSITY_1"),
        pool_name="University electives",
        pool_type=ElectivePoolType.UNIVERSITY_ELECTIVE,
        allowed_courses=(candidate,),
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    result = service().audit(
        request(
            [
                requirement(
                    ElectiveSlotRequirement(
                        ElectiveSlotId(R23, CAIE, "ASU_1"), pool.pool_id
                    ),
                    "SLOT-1",
                ),
                requirement(
                    ElectiveSlotRequirement(
                        ElectiveSlotId(R23, CAIE, "ASU_2"), pool.pool_id
                    ),
                    "SLOT-2",
                ),
            ],
            student_state=student(passed=(candidate,)),
            pools=(pool,),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_NOT_SATISFIED
    assert len(result.satisfied_requirements) == 1
    assert len(result.unsatisfied_requirements) == 1


def test_field_training_is_a_non_course_fact() -> None:
    training = FieldTrainingRequirement(8)
    result = service().audit(
        request(
            [requirement(training)],
            facts=StudentProgramFacts(
                coverage=ProgramFactCoverage.COMPLETE,
                field_training=FieldTrainingRecord(passed=True, completed_weeks=8),
            ),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    assert result.progress.field_training.completed_weeks == 8


def test_missing_field_training_with_unavailable_facts_is_indeterminate() -> None:
    result = service().audit(
        request(
            [requirement(FieldTrainingRequirement(8))],
            facts=StudentProgramFacts(coverage=ProgramFactCoverage.UNAVAILABLE),
        )
    )

    assert result.status is DegreeAuditStatus.HUMAN_REVIEW_REQUIRED


def test_field_training_fewer_weeks_is_unsatisfied() -> None:
    result = service().audit(
        request(
            [requirement(FieldTrainingRequirement(8))],
            facts=StudentProgramFacts(
                coverage=ProgramFactCoverage.COMPLETE,
                field_training=FieldTrainingRecord(passed=True, completed_weeks=7),
            ),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_NOT_SATISFIED


def test_complete_program_facts_without_training_prove_training_unsatisfied() -> None:
    result = service().audit(
        request(
            [requirement(FieldTrainingRequirement(8))],
            facts=StudentProgramFacts(coverage=ProgramFactCoverage.COMPLETE),
        )
    )

    assert result.status is DegreeAuditStatus.ACADEMIC_REQUIREMENTS_NOT_SATISFIED


class UnknownRequirement(RequirementDefinition):
    definition_type = "UNKNOWN_REQUIREMENT"

    def to_dict(self):
        return {"type": self.definition_type}


def test_unknown_typed_requirement_is_not_silently_ignored() -> None:
    result = service().audit(request([requirement(UnknownRequirement())]))

    assert result.status is DegreeAuditStatus.UNSUPPORTED
    assert result.progress.blocking_requirement_ids == ("REQ-1",)


def test_progress_exposes_structured_dimensions_without_percentage() -> None:
    target = course("CSE341")
    result = service().audit(
        request(
            [
                requirement(CourseCompletionRequirement(target)),
                requirement(TotalProgramCreditsRequirement(144), "REQ-144"),
            ],
            student_state=student(passed=(target,), earned=100),
        )
    )

    assert result.progress.required_program_credits == 144
    assert result.progress.remaining_known_credits == 44
    assert not hasattr(result.progress, "completion_percentage")
    assert result.to_dict()["status"] == "ACADEMIC_REQUIREMENTS_NOT_SATISFIED"


def test_audit_order_and_trace_are_deterministic() -> None:
    first = course("CSE341")
    second = course("CSE342")
    requirements = [
        requirement(CourseCompletionRequirement(second), "REQ-2"),
        requirement(CourseCompletionRequirement(first), "REQ-1"),
    ]
    left = service().audit(
        request(requirements, student_state=student(passed=(first,)))
    )
    right = service().audit(
        request(tuple(reversed(requirements)), student_state=student(passed=(first,)))
    )

    assert left.to_dict() == right.to_dict()
