"""Domain contracts for deterministic modeled-requirement audits."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .academic_state import FactStatus
from .course import CourseIdentity
from .electives import Concentration, ElectivePool, ElectivePoolId, ElectiveSlotId
from .evaluation import EvaluationOutcome
from .program_facts import StudentProgramFacts
from .program_progress import (
    ConcentrationProgress,
    FieldTrainingProgress,
    ProgramProgress,
)
from .requirements import (
    ProgramRequirementSet,
    RequirementStage,
    RequirementSetStatus,
)
from .results import ResultMetadata
from .student import StudentState


class DegreeAuditStatus(StrEnum):
    """Outcome of auditing modeled requirements, not official graduation."""

    ACADEMIC_REQUIREMENTS_SATISFIED = "ACADEMIC_REQUIREMENTS_SATISFIED"
    ACADEMIC_REQUIREMENTS_NOT_SATISFIED = "ACADEMIC_REQUIREMENTS_NOT_SATISFIED"
    INDETERMINATE = "INDETERMINATE"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"


class RequirementEvidence:
    """Nominal base for typed per-requirement evidence."""

    __slots__ = ()

    def to_dict(self) -> dict[str, object]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class CourseRequirementEvidence(RequirementEvidence):
    course: CourseIdentity
    pass_status: FactStatus
    registration_status: FactStatus

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        if not isinstance(self.pass_status, FactStatus):
            raise TypeError("pass_status must be a FactStatus")
        if not isinstance(self.registration_status, FactStatus):
            raise TypeError("registration_status must be a FactStatus")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "COURSE",
            "course": self.course.course_id,
            "pass_status": self.pass_status.value,
            "registration_status": self.registration_status.value,
        }


@dataclass(frozen=True, slots=True)
class NumericRequirementEvidence(RequirementEvidence):
    observed: int | float | None
    required: int | float

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "NUMERIC",
            "observed": self.observed,
            "required": self.required,
            "remaining": (
                max(self.required - self.observed, 0)
                if self.observed is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class PoolRequirementEvidence(RequirementEvidence):
    pool_id: ElectivePoolId
    required_count: int
    known_passed_count: int
    unknown_count: int
    maximum_possible_count: int | None
    known_passed_courses: tuple[CourseIdentity, ...] = ()
    unknown_courses: tuple[CourseIdentity, ...] = ()
    allocated_courses: tuple[CourseIdentity, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.pool_id, ElectivePoolId):
            raise TypeError("pool_id must be an ElectivePoolId")
        for name in (
            "required_count",
            "known_passed_count",
            "unknown_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.maximum_possible_count is not None and (
            isinstance(self.maximum_possible_count, bool)
            or not isinstance(self.maximum_possible_count, int)
            or self.maximum_possible_count < 0
        ):
            raise ValueError("maximum_possible_count must be a non-negative integer")
        for name in (
            "known_passed_courses",
            "unknown_courses",
            "allocated_courses",
        ):
            values = tuple(getattr(self, name))
            if not all(isinstance(item, CourseIdentity) for item in values):
                raise TypeError(f"{name} must contain CourseIdentity values")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must not contain duplicates")
            object.__setattr__(
                self,
                name,
                tuple(sorted(values, key=lambda item: item.course_id)),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "POOL",
            "pool_id": self.pool_id.identifier,
            "required_count": self.required_count,
            "known_passed_count": self.known_passed_count,
            "unknown_count": self.unknown_count,
            "maximum_possible_count": self.maximum_possible_count,
            "known_passed_courses": [
                item.course_id for item in self.known_passed_courses
            ],
            "unknown_courses": [item.course_id for item in self.unknown_courses],
            "allocated_courses": [item.course_id for item in self.allocated_courses],
        }


@dataclass(frozen=True, slots=True)
class ConcentrationRequirementEvidence(RequirementEvidence):
    progress: tuple[ConcentrationProgress, ...]

    def __post_init__(self) -> None:
        values = tuple(self.progress)
        if not all(isinstance(item, ConcentrationProgress) for item in values):
            raise TypeError("progress must contain ConcentrationProgress values")
        object.__setattr__(
            self,
            "progress",
            tuple(sorted(values, key=lambda item: item.concentration_id.identifier)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "CONCENTRATION",
            "progress": [item.to_dict() for item in self.progress],
        }


@dataclass(frozen=True, slots=True)
class SlotRequirementEvidence(RequirementEvidence):
    slot_id: ElectiveSlotId
    pool_id: ElectivePoolId | None
    allocated_course: CourseIdentity | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.slot_id, ElectiveSlotId):
            raise TypeError("slot_id must be an ElectiveSlotId")
        if self.pool_id is not None and not isinstance(self.pool_id, ElectivePoolId):
            raise TypeError("pool_id must be an ElectivePoolId or None")
        if self.allocated_course is not None and not isinstance(
            self.allocated_course, CourseIdentity
        ):
            raise TypeError("allocated_course must be a CourseIdentity or None")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "ELECTIVE_SLOT",
            "slot_id": self.slot_id.identifier,
            "pool_id": self.pool_id.identifier if self.pool_id else None,
            "allocated_course": (
                self.allocated_course.course_id if self.allocated_course else None
            ),
        }


@dataclass(frozen=True, slots=True)
class FieldTrainingRequirementEvidence(RequirementEvidence):
    progress: FieldTrainingProgress

    def __post_init__(self) -> None:
        if not isinstance(self.progress, FieldTrainingProgress):
            raise TypeError("progress must be FieldTrainingProgress")

    def to_dict(self) -> dict[str, object]:
        return {"type": "FIELD_TRAINING", "progress": self.progress.to_dict()}


@dataclass(frozen=True, slots=True)
class UnsupportedRequirementEvidence(RequirementEvidence):
    definition_type: str | None

    def __post_init__(self) -> None:
        if self.definition_type is not None and (
            not isinstance(self.definition_type, str)
            or not self.definition_type.strip()
        ):
            raise ValueError("definition_type must be non-empty when provided")

    def to_dict(self) -> dict[str, object]:
        return {"type": "UNSUPPORTED", "definition_type": self.definition_type}


@dataclass(frozen=True, slots=True)
class RequirementEvaluation:
    requirement_id: str
    definition_type: str | None
    outcome: EvaluationOutcome
    metadata: ResultMetadata
    evidence: RequirementEvidence | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.requirement_id, str) or not self.requirement_id.strip():
            raise ValueError("requirement_id must be a non-empty string")
        if self.definition_type is not None and not isinstance(
            self.definition_type, str
        ):
            raise TypeError("definition_type must be a string or None")
        if not isinstance(self.outcome, EvaluationOutcome):
            raise TypeError("outcome must be an EvaluationOutcome")
        if not isinstance(self.metadata, ResultMetadata):
            raise TypeError("metadata must be ResultMetadata")
        if self.metadata.decision_trace is None:
            raise ValueError("requirement evaluation requires a decision trace")
        if self.evidence is not None and not isinstance(
            self.evidence, RequirementEvidence
        ):
            raise TypeError("evidence must be RequirementEvidence or None")

    @property
    def reason_codes(self):
        return self.metadata.reason_codes

    @property
    def requires_human_review(self) -> bool:
        return self.metadata.requires_human_review

    @property
    def provenance(self):
        return self.metadata.provenance

    @property
    def warnings(self):
        return self.metadata.warnings

    @property
    def authoritative(self) -> bool:
        return self.metadata.authoritative

    @property
    def decision_trace(self):
        assert self.metadata.decision_trace is not None
        return self.metadata.decision_trace

    def to_dict(self) -> dict[str, object]:
        return {
            "requirement_id": self.requirement_id,
            "definition_type": self.definition_type,
            "outcome": self.outcome.value,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class DegreeAuditRequest:
    student: StudentState
    requirement_set: ProgramRequirementSet
    stage: RequirementStage = RequirementStage.PROGRAM_COMPLETION
    pools: tuple[ElectivePool, ...] = ()
    concentrations: tuple[Concentration, ...] = ()
    program_facts: StudentProgramFacts = field(default_factory=StudentProgramFacts)

    def __post_init__(self) -> None:
        if not isinstance(self.student, StudentState):
            raise TypeError("student must be a StudentState")
        if not isinstance(self.requirement_set, ProgramRequirementSet):
            raise TypeError("requirement_set must be a ProgramRequirementSet")
        if not isinstance(self.stage, RequirementStage):
            raise TypeError("stage must be a RequirementStage")
        if (
            self.student.regulation is not self.requirement_set.regulation
            or self.student.program != self.requirement_set.program
        ):
            raise ValueError("student and requirement set scopes must match")
        pools = tuple(self.pools)
        concentrations = tuple(self.concentrations)
        if not all(isinstance(item, ElectivePool) for item in pools):
            raise TypeError("pools must contain ElectivePool values")
        if not all(isinstance(item, Concentration) for item in concentrations):
            raise TypeError("concentrations must contain Concentration values")
        if any(
            item.pool_id.regulation is not self.student.regulation
            or item.pool_id.program != self.student.program
            for item in pools
        ):
            raise ValueError("pool scopes must match the student scope")
        if any(
            item.concentration_id.regulation is not self.student.regulation
            or item.concentration_id.program != self.student.program
            for item in concentrations
        ):
            raise ValueError("concentration scopes must match the student scope")
        if len({item.pool_id for item in pools}) != len(pools):
            raise ValueError("pools must have unique IDs")
        if len({item.concentration_id for item in concentrations}) != len(
            concentrations
        ):
            raise ValueError("concentrations must have unique IDs")
        if not isinstance(self.program_facts, StudentProgramFacts):
            raise TypeError("program_facts must be StudentProgramFacts")
        object.__setattr__(
            self,
            "pools",
            tuple(sorted(pools, key=lambda item: item.pool_id.identifier)),
        )
        object.__setattr__(
            self,
            "concentrations",
            tuple(
                sorted(
                    concentrations,
                    key=lambda item: item.concentration_id.identifier,
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class DegreeAuditResult:
    status: DegreeAuditStatus
    requirement_set_status: RequirementSetStatus
    metadata: ResultMetadata
    requirement_results: tuple[RequirementEvaluation, ...]
    progress: ProgramProgress

    def __post_init__(self) -> None:
        if not isinstance(self.status, DegreeAuditStatus):
            raise TypeError("status must be a DegreeAuditStatus")
        if not isinstance(self.requirement_set_status, RequirementSetStatus):
            raise TypeError("requirement_set_status must be a RequirementSetStatus")
        if not isinstance(self.metadata, ResultMetadata):
            raise TypeError("metadata must be ResultMetadata")
        if self.metadata.decision_trace is None:
            raise ValueError("degree audit requires a decision trace")
        results = tuple(self.requirement_results)
        if not all(isinstance(item, RequirementEvaluation) for item in results):
            raise TypeError(
                "requirement_results must contain RequirementEvaluation values"
            )
        if len({item.requirement_id for item in results}) != len(results):
            raise ValueError("requirement result IDs must be unique")
        if not isinstance(self.progress, ProgramProgress):
            raise TypeError("progress must be ProgramProgress")
        object.__setattr__(
            self,
            "requirement_results",
            tuple(sorted(results, key=lambda item: item.requirement_id)),
        )

    @property
    def authoritative(self) -> bool:
        return self.metadata.authoritative

    @property
    def requires_human_review(self) -> bool:
        return self.metadata.requires_human_review

    @property
    def reason_codes(self):
        return self.metadata.reason_codes

    @property
    def satisfied_requirements(self) -> tuple[RequirementEvaluation, ...]:
        return tuple(
            item
            for item in self.requirement_results
            if item.outcome is EvaluationOutcome.SATISFIED
        )

    @property
    def unsatisfied_requirements(self) -> tuple[RequirementEvaluation, ...]:
        return tuple(
            item
            for item in self.requirement_results
            if item.outcome is EvaluationOutcome.UNSATISFIED
        )

    @property
    def indeterminate_requirements(self) -> tuple[RequirementEvaluation, ...]:
        return tuple(
            item
            for item in self.requirement_results
            if item.outcome is EvaluationOutcome.INDETERMINATE
        )

    @property
    def decision_trace(self):
        assert self.metadata.decision_trace is not None
        return self.metadata.decision_trace

    @property
    def requirement_evaluations(self):
        return self.requirement_results

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "requirement_set_status": self.requirement_set_status.value,
            "authoritative": self.metadata.authoritative,
            "requires_human_review": self.metadata.requires_human_review,
            "reason_codes": [reason.value for reason in self.metadata.reason_codes],
            "requirement_results": [
                item.to_dict() for item in self.requirement_results
            ],
            "progress": self.progress.to_dict(),
            "metadata": self.metadata.to_dict(),
        }


__all__ = [
    "ConcentrationRequirementEvidence",
    "CourseRequirementEvidence",
    "DegreeAuditRequest",
    "DegreeAuditResult",
    "DegreeAuditStatus",
    "FieldTrainingRequirementEvidence",
    "NumericRequirementEvidence",
    "PoolRequirementEvidence",
    "RequirementEvaluation",
    "RequirementEvidence",
    "SlotRequirementEvidence",
    "UnsupportedRequirementEvidence",
]
