from pathlib import Path
from dataclasses import replace

import pytest

from backend.app.planning.domain.course import CourseIdentity, Program, Regulation
from backend.app.planning.domain.candidates import (
    CandidateAvailability,
    CandidateGenerationRequest,
    CandidateReasonCode,
)
from backend.app.planning.domain.course import Course
from backend.app.planning.domain.eligibility import (
    CourseEligibilityRuleSet,
    RuleSetStatus,
)
from backend.app.planning.eligibility.service import EligibilityService
from backend.app.planning.rules.evaluator import RuleEvaluator
from backend.app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from backend.app.planning.domain.provenance import Provenance
from backend.app.planning.domain.student import StudentState
from backend.app.planning.domain.uel import (
    UELMapping,
    UELMappingSet,
    UELModuleId,
    UELModuleResult,
    UELModuleStatus,
    UELProgressCoverage,
    UELStudentProgress,
)
from backend.app.planning.domain.version import DatasetVersion
from backend.app.planning.domain.scenario import (
    UELModuleOutcomeScenario,
    WhatIfPlanningRequest,
)
from backend.app.planning.policy import ExecutionPolicy
from backend.app.planning.uel.service import UELProgressService
from backend.app.planning.candidates.service import CandidateGenerator
from backend.app.planning.ranking.service import PriorityRankingService


def _provenance(*, approved: bool = True) -> Provenance:
    return Provenance(
        rule_id="UEL-RULE-1",
        source_id="SRC-UEL-1",
        source_page=5,
        approval_status=(
            ApprovalStatus.APPROVED if approved else ApprovalStatus.SOURCE_VERIFIED
        ),
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )


def _module(code: str = "CN3308") -> UELModuleId:
    return UELModuleId.parse(f"R23:UEL:{code}")


def _course(code: str = "PHM112") -> CourseIdentity:
    return CourseIdentity.parse(f"R23:CAIE:{code}")


def _mapping(
    *,
    module: UELModuleId | None = None,
    course: CourseIdentity | None = None,
    approved: bool = True,
    mapping_id: str = "R23:CN3308:PHM112",
) -> UELMapping:
    return UELMapping(
        mapping_id=mapping_id,
        module=module or _module(),
        course=course or _course(),
        mapping_type="WEIGHTED_COMPONENT",
        weight_percent=60,
        provenance=_provenance(approved=approved),
    )


def _student(*, passed: tuple[str, ...] = ()) -> StudentState:
    return StudentState(
        student_id="uel-student",
        regulation=Regulation.R23,
        program=Program("CAIE"),
        gpa=3.0,
        passed_courses=frozenset(_course(code) for code in passed),
    )


def _progress(
    result: UELModuleResult,
    *,
    coverage: UELProgressCoverage = UELProgressCoverage.COMPLETE,
) -> UELStudentProgress:
    return UELStudentProgress(
        module_results=(result,),
        known_modules=(result.module,),
        coverage=coverage,
    )


def _service(*, authoritative: bool = False) -> UELProgressService:
    return UELProgressService(
        DatasetVersion("uel-test"),
        ExecutionPolicy.authoritative()
        if authoritative
        else ExecutionPolicy.development(),
    )


def test_uel_module_identity_is_separate_from_course_identity() -> None:
    module = _module()

    assert module.module_id == "R23:UEL:CN3308"
    assert str(module) == module.module_id
    assert module != _course()
    with pytest.raises(ValueError):
        UELModuleId.parse("R23:CAIE:CN3308")


def test_explicit_uel_result_is_preserved_and_serializable() -> None:
    result = UELModuleResult(
        module=_module(),
        status=UELModuleStatus.PASSED,
        provenance=_provenance(),
    )

    assert result.status is UELModuleStatus.PASSED
    assert result.to_dict()["module"] == "R23:UEL:CN3308"
    assert result.to_dict()["status"] == "PASSED"


@pytest.mark.parametrize(
    "status",
    [UELModuleStatus.FAILED, UELModuleStatus.IN_PROGRESS, UELModuleStatus.OUTSTANDING],
)
def test_explicit_non_pass_uel_statuses_are_distinct(status: UELModuleStatus) -> None:
    result = UELModuleResult(module=_module(), status=status, provenance=_provenance())

    assert result.status is status


def test_incomplete_or_unavailable_uel_coverage_does_not_infer_failure() -> None:
    progress = UELStudentProgress(
        module_results=(),
        known_modules=(_module(),),
        coverage=UELProgressCoverage.UNAVAILABLE,
    )

    assert progress.result_for(_module()) is None
    assert _module() in progress.unknown_modules


def test_complete_coverage_can_report_known_outstanding_module() -> None:
    progress = UELStudentProgress(
        module_results=(),
        known_modules=(_module(),),
        coverage=UELProgressCoverage.COMPLETE,
    )

    assert progress.result_for(_module()).status is UELModuleStatus.OUTSTANDING
    assert progress.outstanding_modules == (_module(),)


def test_mapping_supports_forward_and_reverse_lookup_deterministically() -> None:
    second = _mapping(
        module=UELModuleId.parse("R23:UEL:CN3309"),
        course=CourseIdentity.parse("R23:CAIE:CSE142"),
        mapping_id="R23:CN3309:CSE142",
    )
    mapping_set = UELMappingSet(
        mappings=(second, _mapping()), coverage=UELProgressCoverage.COMPLETE
    )

    assert mapping_set.courses_for_module(_module()) == (_course(),)
    assert mapping_set.modules_for_course(_course()) == (_module(),)
    assert mapping_set.to_dict()["mappings"][0]["mapping_id"] == "R23:CN3308:PHM112"


def test_asu_pass_and_uel_fail_are_independent() -> None:
    module_result = UELModuleResult(
        module=_module(), status=UELModuleStatus.FAILED, provenance=_provenance()
    )
    evaluation = _service().evaluate(
        student=_student(passed=("PHM112",)),
        progress=_progress(module_result),
        mappings=UELMappingSet((_mapping(),), UELProgressCoverage.COMPLETE),
    )

    assert evaluation.progress.failed_modules == (_module(),)
    assert evaluation.risks[0].mapped_courses == (_course(),)
    assert evaluation.risks[0].level.value == "ATTENTION"


def test_asu_fail_and_uel_pass_are_independent() -> None:
    module_result = UELModuleResult(
        module=_module(), status=UELModuleStatus.PASSED, provenance=_provenance()
    )
    evaluation = _service().evaluate(
        student=_student(),
        progress=_progress(module_result),
        mappings=UELMappingSet((_mapping(),), UELProgressCoverage.COMPLETE),
    )

    assert evaluation.progress.passed_modules == (_module(),)
    assert evaluation.risks == ()


def test_unknown_uel_state_is_not_definite_progression_risk() -> None:
    progress = UELStudentProgress(
        module_results=(
            UELModuleResult(
                module=_module(),
                status=UELModuleStatus.UNKNOWN,
                provenance=_provenance(),
            ),
        ),
        known_modules=(_module(),),
        coverage=UELProgressCoverage.PARTIAL,
    )

    evaluation = _service().evaluate(
        student=_student(),
        progress=progress,
        mappings=UELMappingSet((_mapping(),), UELProgressCoverage.COMPLETE),
    )

    assert evaluation.risks[0].level.value == "UNKNOWN"


def test_unsafe_mapping_cannot_be_authoritative() -> None:
    module_result = UELModuleResult(
        module=_module(), status=UELModuleStatus.FAILED, provenance=_provenance()
    )
    evaluation = _service(authoritative=True).evaluate(
        student=_student(),
        progress=_progress(module_result),
        mappings=UELMappingSet(
            (_mapping(approved=False),), UELProgressCoverage.COMPLETE
        ),
    )

    assert evaluation.metadata.authoritative is False
    assert evaluation.metadata.requires_human_review is True
    assert evaluation.risks[0].level.value == "HUMAN_REVIEW_REQUIRED"


def test_real_normalized_uel_mappings_are_exposed_without_upgrading_tier() -> None:
    from backend.app.planning.repositories.adapters.academic_data_adapter import (
        JsonAcademicDataAdapter,
    )
    from backend.app.planning.repositories.adapters.academic_data_types import (
        AcademicDataConfig,
        AcademicDataSourceMode,
    )

    loaded = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=Path("data/academic"),
            source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
        )
    )
    assert loaded.value is not None
    mapping_set = loaded.value.get_uel_mapping_set(
        regulation=Regulation.R23,
        program=Program("CAIE"),
    )

    assert mapping_set.coverage is UELProgressCoverage.COMPLETE
    assert mapping_set.mappings
    assert mapping_set.mappings[0].provenance.source_id is not None
    assert loaded.value.uel_module_count > 0
    assert loaded.value.uel_module_coverage is UELProgressCoverage.COMPLETE


def test_uel_risk_adds_relevant_course_candidate_reason() -> None:
    module_result = UELModuleResult(
        module=_module(), status=UELModuleStatus.OUTSTANDING, provenance=_provenance()
    )
    uel = _service().evaluate(
        student=_student(),
        progress=_progress(module_result),
        mappings=UELMappingSet((_mapping(),), UELProgressCoverage.COMPLETE),
    )
    target = Course(
        _course(),
        "PHM112",
        3,
        ApprovalStatus.APPROVED,
        VerificationStatus.SOURCE_VERIFIED,
    )
    result = CandidateGenerator(
        EligibilityService(
            RuleEvaluator(ExecutionPolicy.development(), DatasetVersion("candidate"))
        )
    ).generate(
        CandidateGenerationRequest(
            student=_student(),
            courses=(target,),
            rule_sets=(
                CourseEligibilityRuleSet(target.identity, RuleSetStatus.COMPLETE),
            ),
            uel_evaluation=uel,
        )
    )

    assert (
        result.available_candidates[0].availability is CandidateAvailability.AVAILABLE
    )
    assert (
        CandidateReasonCode.UEL_MODULE_OUTSTANDING
        in result.available_candidates[0].reason_codes
    )
    assert result.available_candidates[0].uel_module_ids == (_module(),)
    assert result.available_candidates[0].uel_provenance == (_provenance(),)


def test_uel_progression_risk_is_an_explicit_priority_factor() -> None:
    module_result = UELModuleResult(
        module=_module(), status=UELModuleStatus.FAILED, provenance=_provenance()
    )
    uel = _service().evaluate(
        student=_student(),
        progress=_progress(module_result),
        mappings=UELMappingSet((_mapping(),), UELProgressCoverage.COMPLETE),
    )
    target = Course(
        _course(),
        "PHM112",
        3,
        ApprovalStatus.APPROVED,
        VerificationStatus.SOURCE_VERIFIED,
    )
    candidate = CandidateGenerator(
        EligibilityService(
            RuleEvaluator(ExecutionPolicy.development(), DatasetVersion("candidate"))
        )
    ).generate(
        CandidateGenerationRequest(
            student=_student(),
            courses=(target,),
            rule_sets=(
                CourseEligibilityRuleSet(target.identity, RuleSetStatus.COMPLETE),
            ),
            uel_evaluation=uel,
        )
    )
    ranked = PriorityRankingService(DatasetVersion("ranking")).rank(candidate)

    assert ranked.items[0].factors.external_progression_risk == 1
    assert "external_progression_risk" in ranked.items[0].factors.to_dict()


def test_multi_semester_preserves_uel_awareness_without_projecting_uel_pass() -> None:
    from backend.tests.planning.test_multi_semester_planner import (
        planner,
        request,
        requirement,
        rule_set,
    )

    target = CourseIdentity.parse("R23:CAIE:PHM112")
    student = _student()
    base = request(
        (
            Course(
                target,
                "PHM112",
                3,
                ApprovalStatus.APPROVED,
                VerificationStatus.SOURCE_VERIFIED,
            ),
        ),
        (requirement(target, 1),),
        student_value=student,
        rule_sets=(rule_set(target),),
    )
    module_result = UELModuleResult(
        module=_module(), status=UELModuleStatus.OUTSTANDING, provenance=_provenance()
    )
    evaluation = _service().evaluate(
        student=student,
        progress=_progress(module_result),
        mappings=UELMappingSet(
            (_mapping(course=target),), UELProgressCoverage.COMPLETE
        ),
    )
    base = replace(
        base,
        candidate_request=replace(base.candidate_request, uel_evaluation=evaluation),
    )

    result = planner().plan(base)

    assert result.uel_evaluation is not None
    assert result.uel_evaluation.progress.outstanding_modules == (_module(),)
    assert result.final_state.pass_status(target).value == "KNOWN_TRUE"
    assert result.uel_evaluation.progress.passed_modules == ()
    assert result.coverage.uel.value == "COMPLETE"


def test_uel_outcome_what_if_changes_uel_risk_without_changing_asu_history() -> None:
    from backend.tests.planning.test_multi_semester_planner import (
        planner,
        request,
        requirement,
        rule_set,
    )

    target = CourseIdentity.parse("R23:CAIE:PHM112")
    student = _student()
    base = request(
        (
            Course(
                target,
                "PHM112",
                3,
                ApprovalStatus.APPROVED,
                VerificationStatus.SOURCE_VERIFIED,
            ),
        ),
        (requirement(target, 1),),
        student_value=student,
        rule_sets=(rule_set(target),),
    )
    evaluation = _service().evaluate(
        student=student,
        progress=_progress(
            UELModuleResult(
                module=_module(),
                status=UELModuleStatus.OUTSTANDING,
                provenance=_provenance(),
            )
        ),
        mappings=UELMappingSet(
            (_mapping(course=target),), UELProgressCoverage.COMPLETE
        ),
    )
    base = replace(
        base,
        candidate_request=replace(base.candidate_request, uel_evaluation=evaluation),
    )
    result = (
        __import__(
            "backend.app.planning.scenario.service",
            fromlist=["WhatIfEvaluationService"],
        )
        .WhatIfEvaluationService(planner())
        .evaluate(
            WhatIfPlanningRequest(
                baseline=base,
                scenarios=(
                    UELModuleOutcomeScenario(_module(), UELModuleStatus.PASSED),
                ),
            )
        )
    )

    assert result.baseline.uel_evaluation is not None
    assert result.scenario.uel_evaluation is not None
    assert result.scenario.uel_evaluation.progress.passed_modules == (_module(),)
    assert result.delta.uel_risk_changes[0].baseline.value == "PROGRESSION_RISK"
    assert result.delta.uel_risk_changes[0].scenario.value == "NONE"
    assert student.pass_status(target).value == "KNOWN_FALSE"
