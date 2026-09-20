from __future__ import annotations

from app.planning.domain.course import CourseIdentity, Program, Regulation
from app.planning.domain.electives import (
    ConcentrationId,
    ElectivePoolId,
    ElectiveSlotId,
)
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.requirements import (
    ConcentrationRequirement,
    CourseCompletionRequirement,
    CourseCountFromPoolRequirement,
    ElectiveSlotRequirement,
    EarnedCreditThresholdRequirement,
    FieldTrainingRequirement,
    MinimumGPARequirement,
    ProgramRequirement,
    RequirementStage,
    TotalProgramCreditsRequirement,
    ZeroCreditCourseRequirement,
)
from app.planning.domain.provenance import Provenance


R23 = Regulation.R23
CAIE = Program("CAIE")


def _course(code: str) -> CourseIdentity:
    return CourseIdentity.parse(f"R23:CAIE:{code}")


def test_requirement_definitions_cover_core_and_zero_credit_courses() -> None:
    core = CourseCompletionRequirement(course=_course("CSE341"))
    zero = ZeroCreditCourseRequirement(course=_course("ASUx11"))

    assert core.course == _course("CSE341")
    assert zero.counts_toward_credits is False
    assert zero.counts_toward_gpa is False


def test_technical_elective_and_concentration_requirements_are_typed() -> None:
    pool = ElectivePoolId(R23, CAIE, "TECHNICAL_ELECTIVES")
    technical = CourseCountFromPoolRequirement(
        pool_id=pool,
        required_count=7,
        course_credit_hours=3,
    )
    concentration = ConcentrationRequirement(
        technical_pool_id=pool,
        minimum_count=5,
        concentrations=(
            ConcentrationId(R23, CAIE, "DATA_SCIENCE"),
            ConcentrationId(R23, CAIE, "SOFTWARE_PRODUCT_LINES"),
        ),
    )

    assert technical.required_count == 7
    assert technical.course_credit_hours == 3
    assert concentration.minimum_count == 5
    assert all(
        not isinstance(item, CourseIdentity) for item in concentration.concentrations
    )


def test_elective_slot_is_scoped_and_can_bind_explicitly_to_a_pool() -> None:
    slot = ElectiveSlotId(R23, CAIE, "ASU_ELECTIVE_1")
    pool = ElectivePoolId(R23, CAIE, "UNIVERSITY_ELECTIVES_1")
    definition = ElectiveSlotRequirement(slot_id=slot, pool_id=pool)

    assert definition.slot_id != pool
    assert not isinstance(slot, CourseIdentity)
    assert definition.pool_id == pool


def test_elective_slot_without_pool_binding_remains_unresolved() -> None:
    slot = ElectiveSlotRequirement(
        slot_id=ElectiveSlotId(R23, CAIE, "ASU_ELECTIVE_2"),
        pool_id=None,
    )

    assert slot.pool_id is None


def test_credit_stages_keep_registration_gate_separate_from_completion() -> None:
    gate = EarnedCreditThresholdRequirement(
        minimum_earned_credit_hours=101,
        stage=RequirementStage.REGISTRATION_GATE,
    )
    graduation = TotalProgramCreditsRequirement(
        required_credit_hours=144,
        stage=RequirementStage.PROGRAM_COMPLETION,
    )

    assert gate.stage is RequirementStage.REGISTRATION_GATE
    assert graduation.stage is RequirementStage.PROGRAM_COMPLETION
    assert gate.minimum_earned_credit_hours != graduation.required_credit_hours


def test_gpa_and_field_training_definitions_are_non_course_requirements() -> None:
    gpa = MinimumGPARequirement(minimum_gpa=2.0)
    training = FieldTrainingRequirement(minimum_weeks=8)

    assert gpa.minimum_gpa == 2.0
    assert training.minimum_weeks == 8
    assert training.passed is True
    assert training.counts_toward_gpa is False


def test_governed_requirement_retains_lifecycle_and_provenance() -> None:
    provenance = Provenance(
        rule_id="REQ23-001",
        source_id="SRC-BYLAW_2023_BRIEF_ICHEP_PDF",
        source_page=84,
        approval_status=ApprovalStatus.SOURCE_VERIFIED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    requirement = ProgramRequirement(
        requirement_id="REQ23-001",
        regulation=R23,
        program=CAIE,
        approval_status=ApprovalStatus.SOURCE_VERIFIED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        provenance=provenance,
        definition=TotalProgramCreditsRequirement(144),
    )

    assert requirement.definition is not None
    assert requirement.provenance == provenance


def test_metadata_only_legacy_requirement_is_not_evaluable() -> None:
    requirement = ProgramRequirement(
        requirement_id="legacy",
        regulation=R23,
        program=CAIE,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )

    assert requirement.definition is None
    assert requirement.is_evaluable is False


def test_regulation_scoped_requirement_identity_does_not_collide() -> None:
    r18 = ElectivePoolId(Regulation.R18, Program("CAIE"), "TECHNICAL_ELECTIVES")
    r23 = ElectivePoolId(R23, CAIE, "TECHNICAL_ELECTIVES")

    assert r18 != r23


def test_governed_requirement_rejects_definition_from_another_scope() -> None:
    try:
        ProgramRequirement(
            requirement_id="REQ23-CORE-001",
            regulation=R23,
            program=CAIE,
            approval_status=ApprovalStatus.APPROVED,
            verification_status=VerificationStatus.SOURCE_VERIFIED,
            definition=CourseCompletionRequirement(
                CourseIdentity.parse("R18:CESS:CSE111")
            ),
        )
    except ValueError as error:
        assert "scope" in str(error)
    else:
        raise AssertionError("cross-scope requirement definition must be rejected")
