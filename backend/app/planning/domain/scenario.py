"""Typed, ephemeral scenario contracts for deterministic what-if analysis."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .academic_state import HypotheticalAcademicOutcome
from .conditions import FutureCondition
from .context import RegistrationIntent
from .course import CourseIdentity
from .multi_semester import (
    MultiSemesterPlanResult,
    MultiSemesterPlanStatus,
    MultiSemesterPlanningRequest,
)
from .planning import PlanningPreferences
from .results import ResultMetadata
from .student_history import AttemptOutcome, AttemptPurpose
from .trace import DecisionTrace
from .uel import (
    UELModuleId,
    UELModuleResult,
    UELModuleStatus,
    UELRiskDelta,
)


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    """Base contract for one ordered, non-persistent scenario operation."""

    def to_dict(self) -> dict[str, object]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class CourseOutcomeScenario(ScenarioDefinition):
    """Apply one explicitly supplied hypothetical course outcome."""

    course: CourseIdentity
    outcome: AttemptOutcome
    purpose: AttemptPurpose = AttemptPurpose.UNKNOWN
    earned_credit_hours: int | float | None = None
    intent: RegistrationIntent = RegistrationIntent.NORMAL

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        if not isinstance(self.outcome, AttemptOutcome):
            raise TypeError("outcome must be an AttemptOutcome")
        if not isinstance(self.purpose, AttemptPurpose):
            raise TypeError("purpose must be an AttemptPurpose")
        if self.earned_credit_hours is not None and (
            isinstance(self.earned_credit_hours, bool)
            or not isinstance(self.earned_credit_hours, (int, float))
            or not math.isfinite(self.earned_credit_hours)
            or self.earned_credit_hours < 0
        ):
            raise ValueError("earned_credit_hours must be non-negative numeric or None")
        if not isinstance(self.intent, RegistrationIntent):
            raise TypeError("intent must be a RegistrationIntent")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "COURSE_OUTCOME",
            "course": self.course.course_id,
            "outcome": self.outcome.value,
            "purpose": self.purpose.value,
            "earned_credit_hours": self.earned_credit_hours,
            "intent": self.intent.value,
        }

    def to_hypothetical_outcome(self) -> HypotheticalAcademicOutcome:
        return HypotheticalAcademicOutcome(
            course=self.course,
            outcome=self.outcome,
            purpose=self.purpose,
            earned_credit_hours=self.earned_credit_hours,
            intent=self.intent,
        )


@dataclass(frozen=True, slots=True)
class ExcludeCourseScenario(ScenarioDefinition):
    """Constrain candidate selection without changing academic facts."""

    course: CourseIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")

    def to_dict(self) -> dict[str, object]:
        return {"type": "EXCLUDE_COURSE", "course": self.course.course_id}


@dataclass(frozen=True, slots=True)
class PlanningPreferenceScenario(ScenarioDefinition):
    """Replace planning preferences for the scenario evaluation only."""

    preferences: PlanningPreferences

    def __post_init__(self) -> None:
        if not isinstance(self.preferences, PlanningPreferences):
            raise TypeError("preferences must be PlanningPreferences")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "PLANNING_PREFERENCES",
            "preferences": self.preferences.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PlanningHorizonScenario(ScenarioDefinition):
    """Change the bounded forward-planning horizon for one scenario."""

    max_semesters: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_semesters, bool)
            or not isinstance(self.max_semesters, int)
            or self.max_semesters < 1
        ):
            raise ValueError("max_semesters must be a positive integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "PLANNING_HORIZON",
            "max_semesters": self.max_semesters,
        }


@dataclass(frozen=True, slots=True)
class UELModuleOutcomeScenario(ScenarioDefinition):
    """Supply one explicit UEL outcome without changing ASU course history."""

    module: UELModuleId
    status: UELModuleStatus
    requires_human_review: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.module, UELModuleId):
            raise TypeError("module must be a UELModuleId")
        if not isinstance(self.status, UELModuleStatus):
            raise TypeError("status must be a UELModuleStatus")
        if not isinstance(self.requires_human_review, bool):
            raise TypeError("requires_human_review must be a bool")

    def to_module_result(self) -> UELModuleResult:
        return UELModuleResult(
            module=self.module,
            status=self.status,
            explicit_result=True,
            requires_human_review=self.requires_human_review,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "UEL_MODULE_OUTCOME",
            "module": self.module.module_id,
            "status": self.status.value,
            "requires_human_review": self.requires_human_review,
        }


ScenarioOperation = (
    CourseOutcomeScenario
    | ExcludeCourseScenario
    | PlanningPreferenceScenario
    | PlanningHorizonScenario
    | UELModuleOutcomeScenario
)


@dataclass(frozen=True, slots=True)
class WhatIfPlanningRequest:
    """An ordered, typed scenario applied to a baseline planning request."""

    baseline: MultiSemesterPlanningRequest
    scenarios: tuple[ScenarioOperation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.baseline, MultiSemesterPlanningRequest):
            raise TypeError("baseline must be a MultiSemesterPlanningRequest")
        scenarios = tuple(self.scenarios)
        if not all(isinstance(item, ScenarioDefinition) for item in scenarios):
            raise TypeError("scenarios must contain ScenarioDefinition values")
        object.__setattr__(self, "scenarios", scenarios)

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline": self.baseline.to_dict(),
            "scenarios": [item.to_dict() for item in self.scenarios],
        }


@dataclass(frozen=True, slots=True)
class WhatIfDelta:
    """Meaningful typed differences between two bounded planning results."""

    baseline_status: MultiSemesterPlanStatus
    scenario_status: MultiSemesterPlanStatus
    added_courses: tuple[CourseIdentity, ...] = ()
    removed_courses: tuple[CourseIdentity, ...] = ()
    newly_satisfied_requirements: tuple[str, ...] = ()
    newly_blocking_requirements: tuple[str, ...] = ()
    earned_credit_hours_delta: int | float | None = None
    path_length_delta: int = 0
    new_conditions: tuple[FutureCondition, ...] = ()
    new_review_items: tuple[str, ...] = ()
    uel_risk_changes: tuple[UELRiskDelta, ...] = ()

    def __post_init__(self) -> None:
        for name in ("baseline_status", "scenario_status"):
            value = getattr(self, name)
            if not isinstance(value, MultiSemesterPlanStatus):
                raise TypeError(f"{name} must be a MultiSemesterPlanStatus")
        for name in (
            "added_courses",
            "removed_courses",
        ):
            values = tuple(getattr(self, name))
            if not all(isinstance(item, CourseIdentity) for item in values):
                raise TypeError(f"{name} must contain CourseIdentity values")
            object.__setattr__(
                self,
                name,
                tuple(sorted(set(values), key=lambda item: item.course_id)),
            )
        for name in (
            "newly_satisfied_requirements",
            "newly_blocking_requirements",
            "new_review_items",
        ):
            values = tuple(getattr(self, name))
            if not all(isinstance(item, str) and item.strip() for item in values):
                raise TypeError(f"{name} must contain non-empty strings")
            object.__setattr__(self, name, tuple(sorted(set(values))))
        if self.earned_credit_hours_delta is not None and (
            isinstance(self.earned_credit_hours_delta, bool)
            or not isinstance(self.earned_credit_hours_delta, (int, float))
            or not math.isfinite(self.earned_credit_hours_delta)
        ):
            raise TypeError("earned_credit_hours_delta must be numeric or None")
        if isinstance(self.path_length_delta, bool) or not isinstance(
            self.path_length_delta, int
        ):
            raise TypeError("path_length_delta must be an integer")
        conditions = tuple(self.new_conditions)
        if not all(isinstance(item, FutureCondition) for item in conditions):
            raise TypeError("new_conditions must contain FutureCondition values")
        object.__setattr__(
            self,
            "new_conditions",
            tuple(
                sorted(
                    conditions,
                    key=lambda item: repr(item.to_dict()),
                )
            ),
        )
        risk_changes = tuple(self.uel_risk_changes)
        if not all(isinstance(item, UELRiskDelta) for item in risk_changes):
            raise TypeError("uel_risk_changes must contain UELRiskDelta values")
        object.__setattr__(
            self,
            "uel_risk_changes",
            tuple(sorted(risk_changes, key=lambda item: item.module.module_id)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline_status": self.baseline_status.value,
            "scenario_status": self.scenario_status.value,
            "added_courses": [item.course_id for item in self.added_courses],
            "removed_courses": [item.course_id for item in self.removed_courses],
            "newly_satisfied_requirements": list(self.newly_satisfied_requirements),
            "newly_blocking_requirements": list(self.newly_blocking_requirements),
            "earned_credit_hours_delta": self.earned_credit_hours_delta,
            "path_length_delta": self.path_length_delta,
            "new_conditions": [item.to_dict() for item in self.new_conditions],
            "new_review_items": list(self.new_review_items),
            "uel_risk_changes": [item.to_dict() for item in self.uel_risk_changes],
        }


@dataclass(frozen=True, slots=True)
class WhatIfResult:
    """Baseline, scenario, and structured delta for a what-if evaluation."""

    baseline: MultiSemesterPlanResult
    scenario: MultiSemesterPlanResult
    delta: WhatIfDelta
    scenarios: tuple[ScenarioOperation, ...]
    metadata: ResultMetadata
    trace: DecisionTrace

    def __post_init__(self) -> None:
        if not isinstance(self.baseline, MultiSemesterPlanResult):
            raise TypeError("baseline must be a MultiSemesterPlanResult")
        if not isinstance(self.scenario, MultiSemesterPlanResult):
            raise TypeError("scenario must be a MultiSemesterPlanResult")
        if not isinstance(self.delta, WhatIfDelta):
            raise TypeError("delta must be a WhatIfDelta")
        scenarios = tuple(self.scenarios)
        if not all(isinstance(item, ScenarioDefinition) for item in scenarios):
            raise TypeError("scenarios must contain ScenarioDefinition values")
        if not isinstance(self.metadata, ResultMetadata):
            raise TypeError("metadata must be ResultMetadata")
        if not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace")
        object.__setattr__(self, "scenarios", scenarios)

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline": self.baseline.to_dict(),
            "scenario": self.scenario.to_dict(),
            "delta": self.delta.to_dict(),
            "scenarios": [item.to_dict() for item in self.scenarios],
            "metadata": self.metadata.to_dict(),
            "trace": self.trace.to_dict(),
        }


__all__ = [
    "CourseOutcomeScenario",
    "ExcludeCourseScenario",
    "PlanningHorizonScenario",
    "PlanningPreferenceScenario",
    "UELModuleOutcomeScenario",
    "ScenarioDefinition",
    "ScenarioOperation",
    "WhatIfDelta",
    "WhatIfPlanningRequest",
    "WhatIfResult",
]
