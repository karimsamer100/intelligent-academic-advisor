"""Backend application adapter for the typed Planning Engine facade."""

from __future__ import annotations

from collections.abc import Iterable

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


class PlanningService:
    """Thin backend boundary over the public ``PlanningEngine`` facade."""

    def __init__(self, engine: PlanningEngine) -> None:
        if not isinstance(engine, PlanningEngine):
            raise TypeError("engine must be a PlanningEngine")
        self._engine = engine

    def check_eligibility(self, request: EligibilityRequest) -> EligibilityResult:
        return self._engine.check_eligibility(request)

    def audit(self, request: DegreeAuditRequest) -> DegreeAuditResult:
        return self._engine.audit(request)

    def program_progress(self, request: DegreeAuditRequest) -> ProgramProgress:
        return self._engine.program_progress(request)

    def validate_semester(
        self, request: SemesterValidationRequest
    ) -> SemesterValidationResult:
        return self._engine.validate_semester(request)

    def generate_candidates(
        self, request: CandidateGenerationRequest
    ) -> CandidateGenerationResult:
        return self._engine.generate_candidates(request)

    def rank_candidates(
        self,
        candidates: CandidateGenerationResult | Iterable[CandidateCourse],
    ) -> PriorityRankingResult:
        return self._engine.rank_candidates(candidates)

    def plan_semester(
        self, request: SingleSemesterPlanningRequest
    ) -> SingleSemesterPlanResult:
        return self._engine.plan_semester(request)

    def plan_multi_semester(
        self, request: MultiSemesterPlanningRequest
    ) -> MultiSemesterPlanResult:
        return self._engine.plan_multi_semester(request)

    def evaluate_what_if(self, request: WhatIfPlanningRequest) -> WhatIfResult:
        return self._engine.evaluate_what_if(request)

    def evaluate_uel_progress(
        self, request: UELProgressRequest
    ) -> UELProgressEvaluationResult:
        return self._engine.evaluate_uel_progress(request)


__all__ = ["PlanningService"]
