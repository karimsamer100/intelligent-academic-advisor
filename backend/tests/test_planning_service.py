from __future__ import annotations

from typing import cast, get_type_hints
from unittest.mock import Mock, sentinel

from app.planning.domain.audit import DegreeAuditRequest, DegreeAuditResult
from app.planning.domain.candidates import (
    CandidateCourse,
    CandidateGenerationRequest,
    CandidateGenerationResult,
)
from app.planning.domain.eligibility import EligibilityRequest, EligibilityResult
from app.planning.domain.multi_semester import (
    MultiSemesterPlanResult,
    MultiSemesterPlanningRequest,
)
from app.planning.domain.planning import (
    SingleSemesterPlanResult,
    SingleSemesterPlanningRequest,
)
from app.planning.domain.program_progress import ProgramProgress
from app.planning.domain.ranking import PriorityRankingResult
from app.planning.domain.scenario import WhatIfPlanningRequest, WhatIfResult
from app.planning.domain.semester import (
    SemesterValidationRequest,
    SemesterValidationResult,
)
from app.planning.domain.uel import (
    UELProgressEvaluationResult,
    UELProgressRequest,
)
from app.planning.engine import PlanningEngine
from app.services.planning_service import PlanningService


def test_planning_service_accepts_a_concrete_planning_engine() -> None:
    engine = Mock(spec=PlanningEngine)
    service = PlanningService(cast(PlanningEngine, engine))

    assert isinstance(service, PlanningService)


def test_planning_service_delegates_all_facade_capabilities_unchanged() -> None:
    engine = Mock(spec=PlanningEngine)
    service = PlanningService(cast(PlanningEngine, engine))
    calls = (
        (
            "check_eligibility",
            cast(EligibilityRequest, object()),
            sentinel.eligibility,
        ),
        ("audit", cast(DegreeAuditRequest, object()), sentinel.audit),
        (
            "program_progress",
            cast(DegreeAuditRequest, object()),
            sentinel.program_progress,
        ),
        (
            "validate_semester",
            cast(SemesterValidationRequest, object()),
            sentinel.semester,
        ),
        (
            "generate_candidates",
            cast(CandidateGenerationRequest, object()),
            sentinel.candidates,
        ),
        (
            "rank_candidates",
            cast(CandidateGenerationResult | tuple[CandidateCourse, ...], object()),
            sentinel.ranking,
        ),
        (
            "plan_semester",
            cast(SingleSemesterPlanningRequest, object()),
            sentinel.single_semester,
        ),
        (
            "plan_multi_semester",
            cast(MultiSemesterPlanningRequest, object()),
            sentinel.multi_semester,
        ),
        (
            "evaluate_what_if",
            cast(WhatIfPlanningRequest, object()),
            sentinel.what_if,
        ),
        (
            "evaluate_uel_progress",
            cast(UELProgressRequest, object()),
            sentinel.uel,
        ),
    )

    for method_name, request, expected in calls:
        facade_method = getattr(engine, method_name)
        facade_method.return_value = expected

        actual = getattr(service, method_name)(request)

        assert actual is expected
        facade_method.assert_called_once_with(request)


def test_planning_service_contract_annotations_use_public_types() -> None:
    expected_returns = {
        "check_eligibility": EligibilityResult,
        "audit": DegreeAuditResult,
        "program_progress": ProgramProgress,
        "validate_semester": SemesterValidationResult,
        "generate_candidates": CandidateGenerationResult,
        "rank_candidates": PriorityRankingResult,
        "plan_semester": SingleSemesterPlanResult,
        "plan_multi_semester": MultiSemesterPlanResult,
        "evaluate_what_if": WhatIfResult,
        "evaluate_uel_progress": UELProgressEvaluationResult,
    }

    assert get_type_hints(PlanningService.__init__)["engine"] is PlanningEngine
    for method_name, expected_return in expected_returns.items():
        assert get_type_hints(getattr(PlanningService, method_name))["return"] is (
            expected_return
        )
