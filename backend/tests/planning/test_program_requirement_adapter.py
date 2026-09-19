from __future__ import annotations

from pathlib import Path

from backend.app.planning.domain.course import Program, Regulation
from backend.app.planning.domain.course import CourseIdentity
from backend.app.planning.domain.electives import ElectivePoolType
from backend.app.planning.domain.audit import DegreeAuditRequest, DegreeAuditStatus
from backend.app.planning.domain.academic_state import (
    AcademicHistoryCoverage,
    RegistrationCoverage,
)
from backend.app.planning.domain.student import StudentState
from backend.app.planning.domain.version import DatasetVersion
from backend.app.planning.audit.service import DegreeAuditService
from backend.app.planning.domain.requirements import (
    ConcentrationRequirement,
    CourseCountFromPoolRequirement,
    EarnedCreditThresholdRequirement,
    FieldTrainingRequirement,
    MinimumGPARequirement,
    TotalProgramCreditsRequirement,
)
from backend.app.planning.repositories.adapters.academic_data_adapter import (
    JsonAcademicDataAdapter,
)
from backend.app.planning.repositories.adapters.academic_data_types import (
    AcademicDataConfig,
    AcademicDataSourceMode,
)
from backend.app.planning.policy import ExecutionPolicy


def _adapter() -> JsonAcademicDataAdapter:
    result = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=Path("data/academic"),
            source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
        )
    )
    assert result.value is not None
    return result.value


def test_normalized_program_requirements_map_to_typed_definitions() -> None:
    requirements = _adapter().list_requirements(
        regulation=Regulation.R23,
        program=Program("CAIE"),
    )
    by_id = {requirement.requirement_id: requirement for requirement in requirements}

    assert isinstance(by_id["REQ23-001"].definition, TotalProgramCreditsRequirement)
    assert by_id["REQ23-001"].definition.required_credit_hours == 144  # type: ignore[union-attr]
    assert isinstance(by_id["REQ23-002"].definition, MinimumGPARequirement)
    assert isinstance(by_id["REQ23-005"].definition, FieldTrainingRequirement)
    assert isinstance(by_id["REQ23-007"].definition, CourseCountFromPoolRequirement)
    assert isinstance(by_id["REQ23-010"].definition, ConcentrationRequirement)
    assert by_id["REQ23-008"].definition is None
    assert by_id["REQ23-009"].definition is None
    assert by_id["REQ23-008"].approval_status.value == "BLOCKED"
    assert by_id["REQ23-009"].approval_status.value == "BLOCKED"


def test_normalized_elective_pools_remain_scoped_and_lifecycle_aware() -> None:
    pools = _adapter().list_elective_pools(
        regulation=Regulation.R23,
        program=Program("CAIE"),
    )
    technical = next(
        pool for pool in pools if pool.pool_id.value == "TECHNICAL_ELECTIVES"
    )

    assert technical.pool_type is ElectivePoolType.PROGRAM_TECHNICAL_ELECTIVES
    assert technical.required_course_count == 7
    assert technical.approval_status.value == "BLOCKED"
    assert all(
        course.regulation is Regulation.R23 and course.program == Program("CAIE")
        for course in technical.allowed_courses
    )
    concentration_names = {
        pool.pool_name
        for pool in pools
        if pool.pool_type is ElectivePoolType.CONCENTRATION
    }
    assert concentration_names == {
        "Multimedia and Computer Graphics",
        "Distributed and Mobile Computing",
        "Software Product Lines",
        "Data Science",
    }


def test_adapter_does_not_synthesize_absent_101_gate_or_asux11_course() -> None:
    adapter = _adapter()
    requirements = adapter.list_requirements(
        regulation=Regulation.R23,
        program=Program("CAIE"),
    )

    assert not any(
        isinstance(requirement.definition, EarnedCreditThresholdRequirement)
        and requirement.definition.minimum_earned_credit_hours == 101
        for requirement in requirements
    )
    assert adapter.get_course(CourseIdentity.parse("R23:CAIE:ASUx11")).value is None


def test_real_blocked_requirement_data_cannot_produce_authoritative_audit() -> None:
    adapter = _adapter()
    requirement_set = adapter.get_requirement_set(
        regulation=Regulation.R23,
        program=Program("CAIE"),
    )
    result = DegreeAuditService(
        ExecutionPolicy.authoritative(),
        DatasetVersion("real-adapter-audit-test"),
    ).audit(
        DegreeAuditRequest(
            student=StudentState(
                student_id="real-adapter-student",
                regulation=Regulation.R23,
                program=Program("CAIE"),
                earned_credit_hours=144,
                gpa=4.0,
                history_coverage=AcademicHistoryCoverage.COMPLETE,
                registration_coverage=RegistrationCoverage.COMPLETE,
            ),
            requirement_set=requirement_set,
            pools=adapter.list_elective_pools(
                regulation=Regulation.R23,
                program=Program("CAIE"),
            ),
        )
    )

    assert requirement_set.status.value == "INCOMPLETE"
    assert result.status is not DegreeAuditStatus.ACADEMIC_REQUIREMENTS_SATISFIED
    assert result.metadata.authoritative is False
