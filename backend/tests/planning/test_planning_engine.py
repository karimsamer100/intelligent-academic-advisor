from app.planning.domain.course import CourseIdentity, Program, Regulation
from app.planning.domain.uel import (
    UELMapping,
    UELMappingSet,
    UELModuleId,
    UELModuleResult,
    UELModuleStatus,
    UELProgressRequest,
    UELProgressCoverage,
    UELStudentProgress,
)
from app.planning.domain.version import DatasetVersion
from app.planning.domain.provenance import Provenance
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.student import StudentState
from app.planning.eligibility.service import EligibilityService
from app.planning.policy import ExecutionPolicy
from app.planning.rules.evaluator import RuleEvaluator
from app.planning.uel.service import UELProgressService
from app.planning.engine import PlanningEngine


def test_engine_delegates_uel_progress_without_recomputing_academic_truth() -> None:
    version = DatasetVersion("engine-test")
    student = StudentState(
        "engine-student", Regulation.R23, Program("CAIE"), passed_courses=frozenset()
    )
    module = UELModuleId.parse("R23:UEL:CN3308")
    course = CourseIdentity.parse("R23:CAIE:PHM112")
    provenance = Provenance(
        source_id="SRC-ENGINE",
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    progress = UELStudentProgress(
        module_results=(
            UELModuleResult(module, UELModuleStatus.PASSED, provenance=provenance),
        ),
        known_modules=(module,),
        coverage=UELProgressCoverage.COMPLETE,
    )
    mappings = UELMappingSet(
        (
            UELMapping(
                "MAP-ENGINE",
                module,
                course,
                "WEIGHTED_COMPONENT",
                60,
                provenance,
            ),
        ),
        UELProgressCoverage.COMPLETE,
    )
    uel_service = UELProgressService(version, ExecutionPolicy.development())
    engine = PlanningEngine(
        eligibility_service=EligibilityService(
            RuleEvaluator(ExecutionPolicy.development(), version)
        ),
        uel_progress_service=uel_service,
    )

    result = engine.evaluate_uel_progress(
        UELProgressRequest(student=student, progress=progress, mappings=mappings)
    )
    direct = uel_service.evaluate(student=student, progress=progress, mappings=mappings)

    assert result.to_dict() == direct.to_dict()
    assert result.metadata.authoritative is False
