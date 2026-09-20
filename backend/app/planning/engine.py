"""Stable application facade over deterministic Planning Engine services."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable

from .audit.service import DegreeAuditService
from .candidates.service import CandidateGenerator
from .domain.audit import DegreeAuditRequest, DegreeAuditResult
from .domain.candidates import (
    CandidateCourse,
    CandidateGenerationRequest,
    CandidateGenerationResult,
)
from .domain.eligibility import (
    EligibilityRequest,
    EligibilityResult,
)
from .domain.multi_semester import (
    MultiSemesterPlanResult,
    MultiSemesterPlanningRequest,
)
from .domain.planning import (
    SingleSemesterPlanResult,
    SingleSemesterPlanningRequest,
)
from .domain.program_progress import ProgramProgress
from .domain.ranking import PriorityRankingResult
from .domain.scenario import WhatIfPlanningRequest, WhatIfResult
from .domain.semester import (
    SemesterValidationRequest,
    SemesterValidationResult,
)
from .domain.uel import (
    UELProgressEvaluationResult,
    UELProgressRequest,
)
from .eligibility.service import EligibilityService
from .multi_semester.service import MultiSemesterPlanner
from .planner.service import SingleSemesterPlanner
from .ranking.service import PriorityRankingService
from .scenario.service import WhatIfEvaluationService
from .semester.service import SemesterValidator
from .uel.service import UELProgressService


@dataclass(frozen=True, slots=True)
class PlanningEngine:
    """Typed entry point for future API/tool orchestration.

    The facade only delegates to already-owned services.  It deliberately
    accepts typed domain requests and never parses raw user or LLM input.
    Components can be assembled incrementally while the individual services
    remain independently testable.
    """

    eligibility_service: EligibilityService
    degree_audit_service: DegreeAuditService | None = None
    semester_validator: SemesterValidator | None = None
    candidate_generator: CandidateGenerator | None = None
    priority_ranker: PriorityRankingService | None = None
    single_semester_planner: SingleSemesterPlanner | None = None
    multi_semester_planner: MultiSemesterPlanner | None = None
    what_if_service: WhatIfEvaluationService | None = None
    uel_progress_service: UELProgressService | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.eligibility_service, EligibilityService):
            raise TypeError("eligibility_service must be an EligibilityService")
        _check_optional(
            self.degree_audit_service, DegreeAuditService, "degree_audit_service"
        )
        _check_optional(
            self.semester_validator, SemesterValidator, "semester_validator"
        )
        _check_optional(
            self.candidate_generator, CandidateGenerator, "candidate_generator"
        )
        _check_optional(self.priority_ranker, PriorityRankingService, "priority_ranker")
        _check_optional(
            self.single_semester_planner,
            SingleSemesterPlanner,
            "single_semester_planner",
        )
        _check_optional(
            self.multi_semester_planner,
            MultiSemesterPlanner,
            "multi_semester_planner",
        )
        _check_optional(
            self.what_if_service, WhatIfEvaluationService, "what_if_service"
        )
        _check_optional(
            self.uel_progress_service,
            UELProgressService,
            "uel_progress_service",
        )

    def check_eligibility(self, request: EligibilityRequest) -> EligibilityResult:
        return self.eligibility_service.check(request)

    def audit(self, request: DegreeAuditRequest) -> DegreeAuditResult:
        return self._require(self.degree_audit_service, "degree_audit_service").audit(
            request
        )

    def program_progress(self, request: DegreeAuditRequest) -> ProgramProgress:
        """Expose the audit's structured progress without duplicating evaluation."""

        return self.audit(request).progress

    def validate_semester(
        self, request: SemesterValidationRequest
    ) -> SemesterValidationResult:
        return self._require(self.semester_validator, "semester_validator").validate(
            request
        )

    def generate_candidates(
        self, request: CandidateGenerationRequest
    ) -> CandidateGenerationResult:
        return self._require(self.candidate_generator, "candidate_generator").generate(
            request
        )

    def rank_candidates(
        self,
        candidates: CandidateGenerationResult | Iterable[CandidateCourse],
    ) -> PriorityRankingResult:
        return self._require(self.priority_ranker, "priority_ranker").rank(candidates)

    def plan_semester(
        self, request: SingleSemesterPlanningRequest
    ) -> SingleSemesterPlanResult:
        return self._require(
            self.single_semester_planner, "single_semester_planner"
        ).plan(request)

    def plan_multi_semester(
        self, request: MultiSemesterPlanningRequest
    ) -> MultiSemesterPlanResult:
        return self._require(
            self.multi_semester_planner, "multi_semester_planner"
        ).plan(request)

    def evaluate_what_if(self, request: WhatIfPlanningRequest) -> WhatIfResult:
        return self._require(self.what_if_service, "what_if_service").evaluate(request)

    def evaluate_uel_progress(
        self,
        request: UELProgressRequest,
    ) -> UELProgressEvaluationResult:
        return self._require(
            self.uel_progress_service, "uel_progress_service"
        ).evaluate(
            student=request.student,
            progress=request.progress,
            mappings=request.mappings,
        )

    @staticmethod
    def _require(component, name: str):
        if component is None:
            raise RuntimeError(f"PlanningEngine component is not configured: {name}")
        return component


def _check_optional(value: object, expected: type, name: str) -> None:
    if value is not None and not isinstance(value, expected):
        raise TypeError(f"{name} must be a {expected.__name__} or None")


__all__ = ["PlanningEngine"]
