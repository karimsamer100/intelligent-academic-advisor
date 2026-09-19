"""Typed governed program-requirement definitions.

Definitions describe requirement semantics only.  Degree Audit is responsible
for evaluating them against a student in a later task.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from .course import CourseIdentity, Program, Regulation
from .electives import ConcentrationId, ElectivePoolId, ElectiveSlotId
from .lifecycle import ApprovalStatus, VerificationStatus
from .provenance import Provenance
from .reasons import ReasonCode
from .version import DatasetVersion


class RequirementStage(StrEnum):
    """Academic stage to prevent registration gates and graduation totals mixing."""

    PROGRAM_COMPLETION = "PROGRAM_COMPLETION"
    REGISTRATION_GATE = "REGISTRATION_GATE"


class RequirementSetStatus(StrEnum):
    """Coverage of a governed program-requirement collection."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class RequirementDefinition:
    """Nominal base for typed requirement definitions."""

    __slots__ = ()
    definition_type: str

    def to_dict(self) -> dict[str, object]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class CourseCompletionRequirement(RequirementDefinition):
    course: CourseIdentity
    definition_type = "COURSE_COMPLETION"

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")

    def to_dict(self) -> dict[str, object]:
        return {"type": self.definition_type, "course": self.course.course_id}


@dataclass(frozen=True, slots=True)
class ZeroCreditCourseRequirement(RequirementDefinition):
    course: CourseIdentity
    counts_toward_credits: bool = False
    counts_toward_gpa: bool = False
    definition_type = "ZERO_CREDIT_COURSE"

    def __post_init__(self) -> None:
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        if not isinstance(self.counts_toward_credits, bool):
            raise TypeError("counts_toward_credits must be a bool")
        if not isinstance(self.counts_toward_gpa, bool):
            raise TypeError("counts_toward_gpa must be a bool")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.definition_type,
            "course": self.course.course_id,
            "counts_toward_credits": self.counts_toward_credits,
            "counts_toward_gpa": self.counts_toward_gpa,
        }


@dataclass(frozen=True, slots=True)
class CourseCountFromPoolRequirement(RequirementDefinition):
    pool_id: ElectivePoolId
    required_count: int
    course_credit_hours: int | float | None = None
    definition_type = "COURSE_COUNT_FROM_POOL"

    def __post_init__(self) -> None:
        if not isinstance(self.pool_id, ElectivePoolId):
            raise TypeError("pool_id must be an ElectivePoolId")
        if (
            isinstance(self.required_count, bool)
            or not isinstance(self.required_count, int)
            or self.required_count < 0
        ):
            raise ValueError("required_count must be a non-negative integer")
        _validate_optional_nonnegative_number(
            self.course_credit_hours, "course_credit_hours"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.definition_type,
            "pool_id": self.pool_id.identifier,
            "required_count": self.required_count,
            "course_credit_hours": self.course_credit_hours,
        }


@dataclass(frozen=True, slots=True)
class ConcentrationRequirement(RequirementDefinition):
    technical_pool_id: ElectivePoolId
    minimum_count: int
    concentrations: tuple[ConcentrationId, ...] = ()
    definition_type = "CONCENTRATION_MINIMUM"

    def __post_init__(self) -> None:
        if not isinstance(self.technical_pool_id, ElectivePoolId):
            raise TypeError("technical_pool_id must be an ElectivePoolId")
        if (
            isinstance(self.minimum_count, bool)
            or not isinstance(self.minimum_count, int)
            or self.minimum_count < 0
        ):
            raise ValueError("minimum_count must be a non-negative integer")
        concentrations = tuple(self.concentrations)
        if not all(isinstance(item, ConcentrationId) for item in concentrations):
            raise TypeError("concentrations must contain ConcentrationId values")
        if any(
            item.regulation is not self.technical_pool_id.regulation
            or item.program != self.technical_pool_id.program
            for item in concentrations
        ):
            raise ValueError("concentration scope must match technical pool scope")
        if len(concentrations) != len(set(concentrations)):
            raise ValueError("concentrations must not contain duplicates")
        object.__setattr__(
            self,
            "concentrations",
            tuple(sorted(concentrations, key=lambda item: item.identifier)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.definition_type,
            "technical_pool_id": self.technical_pool_id.identifier,
            "minimum_count": self.minimum_count,
            "concentrations": [item.identifier for item in self.concentrations],
        }


@dataclass(frozen=True, slots=True)
class ElectiveSlotRequirement(RequirementDefinition):
    slot_id: ElectiveSlotId
    pool_id: ElectivePoolId | None = None
    definition_type = "ELECTIVE_SLOT"

    def __post_init__(self) -> None:
        if not isinstance(self.slot_id, ElectiveSlotId):
            raise TypeError("slot_id must be an ElectiveSlotId")
        if self.pool_id is not None and not isinstance(self.pool_id, ElectivePoolId):
            raise TypeError("pool_id must be an ElectivePoolId or None")
        if self.pool_id is not None and (
            self.pool_id.regulation is not self.slot_id.regulation
            or self.pool_id.program != self.slot_id.program
        ):
            raise ValueError("slot and pool scope must match")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.definition_type,
            "slot_id": self.slot_id.identifier,
            "pool_id": self.pool_id.identifier if self.pool_id else None,
        }


@dataclass(frozen=True, slots=True)
class EarnedCreditThresholdRequirement(RequirementDefinition):
    minimum_earned_credit_hours: int | float
    stage: RequirementStage = RequirementStage.REGISTRATION_GATE
    definition_type = "EARNED_CREDIT_THRESHOLD"

    def __post_init__(self) -> None:
        _validate_nonnegative_number(
            self.minimum_earned_credit_hours,
            "minimum_earned_credit_hours",
        )
        if not isinstance(self.stage, RequirementStage):
            raise TypeError("stage must be a RequirementStage")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.definition_type,
            "minimum_earned_credit_hours": self.minimum_earned_credit_hours,
            "stage": self.stage.value,
        }


@dataclass(frozen=True, slots=True)
class MinimumGPARequirement(RequirementDefinition):
    minimum_gpa: int | float
    definition_type = "MINIMUM_GPA"

    def __post_init__(self) -> None:
        _validate_number(self.minimum_gpa, "minimum_gpa")

    def to_dict(self) -> dict[str, object]:
        return {"type": self.definition_type, "minimum_gpa": self.minimum_gpa}


@dataclass(frozen=True, slots=True)
class FieldTrainingRequirement(RequirementDefinition):
    minimum_weeks: int
    passed: bool = True
    counts_toward_gpa: bool = False
    definition_type = "FIELD_TRAINING"

    def __post_init__(self) -> None:
        if (
            isinstance(self.minimum_weeks, bool)
            or not isinstance(self.minimum_weeks, int)
            or self.minimum_weeks < 0
        ):
            raise ValueError("minimum_weeks must be a non-negative integer")
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be a bool")
        if not isinstance(self.counts_toward_gpa, bool):
            raise TypeError("counts_toward_gpa must be a bool")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.definition_type,
            "minimum_weeks": self.minimum_weeks,
            "passed": self.passed,
            "counts_toward_gpa": self.counts_toward_gpa,
        }


@dataclass(frozen=True, slots=True)
class TotalProgramCreditsRequirement(RequirementDefinition):
    required_credit_hours: int | float
    stage: RequirementStage = RequirementStage.PROGRAM_COMPLETION
    definition_type = "TOTAL_PROGRAM_CREDITS"

    def __post_init__(self) -> None:
        _validate_nonnegative_number(
            self.required_credit_hours,
            "required_credit_hours",
        )
        if not isinstance(self.stage, RequirementStage):
            raise TypeError("stage must be a RequirementStage")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.definition_type,
            "required_credit_hours": self.required_credit_hours,
            "stage": self.stage.value,
        }


@dataclass(frozen=True, slots=True)
class ProgramRequirement:
    """Requirement identity and safety metadata without evaluation behavior."""

    requirement_id: str
    regulation: Regulation
    program: Program
    approval_status: ApprovalStatus
    verification_status: VerificationStatus
    provenance: Provenance | None = None
    definition: RequirementDefinition | None = None
    critical_for_planner: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.requirement_id, str) or not self.requirement_id.strip():
            raise ValueError("requirement_id must be a non-empty string")
        if not isinstance(self.regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(self.program, Program):
            raise TypeError("program must be a Program")
        if not isinstance(self.approval_status, ApprovalStatus):
            raise TypeError("approval_status must be an ApprovalStatus")
        if not isinstance(self.verification_status, VerificationStatus):
            raise TypeError("verification_status must be a VerificationStatus")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")
        if self.definition is not None and not isinstance(
            self.definition, RequirementDefinition
        ):
            raise TypeError("definition must be a RequirementDefinition or None")
        if not isinstance(self.critical_for_planner, bool):
            raise TypeError("critical_for_planner must be a bool")
        if self.definition is not None:
            _validate_definition_scope(self.definition, self.regulation, self.program)

    @property
    def is_evaluable(self) -> bool:
        """Whether a typed definition exists for future audit evaluation."""

        return self.definition is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "requirement_id": self.requirement_id,
            "regulation": self.regulation.value,
            "program": str(self.program),
            "approval_status": self.approval_status.value,
            "verification_status": self.verification_status.value,
            "critical_for_planner": self.critical_for_planner,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "definition": self.definition.to_dict() if self.definition else None,
        }


@dataclass(frozen=True, slots=True)
class ProgramRequirementSet:
    """Governed, explicitly covered requirements for one program scope.

    An empty ``requirements`` tuple is meaningful only when ``status`` is
    ``COMPLETE``.  ``INCOMPLETE`` and ``UNAVAILABLE`` preserve the fact that
    absence of supplied records cannot be interpreted as absence of academic
    requirements.
    """

    regulation: Regulation
    program: Program
    requirements: tuple[ProgramRequirement, ...]
    status: RequirementSetStatus
    dataset_version: DatasetVersion | None = None
    provenance: tuple[Provenance, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(self.program, Program):
            raise TypeError("program must be a Program")
        if not isinstance(self.status, RequirementSetStatus):
            raise TypeError("status must be a RequirementSetStatus")
        requirements = tuple(self.requirements)
        if not all(isinstance(item, ProgramRequirement) for item in requirements):
            raise TypeError("requirements must contain ProgramRequirement values")
        if any(
            item.regulation is not self.regulation or item.program != self.program
            for item in requirements
        ):
            raise ValueError("all requirements must match the requirement-set scope")
        if len({item.requirement_id for item in requirements}) != len(requirements):
            raise ValueError("requirement IDs must be unique within a requirement set")
        if self.dataset_version is not None and not isinstance(
            self.dataset_version, DatasetVersion
        ):
            raise TypeError("dataset_version must be a DatasetVersion or None")
        provenance = tuple(self.provenance)
        if not all(isinstance(item, Provenance) for item in provenance):
            raise TypeError("provenance must contain Provenance values")
        reason_codes = tuple(
            sorted(set(self.reason_codes), key=lambda item: item.value)
        )
        if not all(isinstance(item, ReasonCode) for item in reason_codes):
            raise TypeError("reason_codes must contain ReasonCode values")
        object.__setattr__(
            self,
            "requirements",
            tuple(sorted(requirements, key=lambda item: item.requirement_id)),
        )
        object.__setattr__(
            self,
            "provenance",
            tuple(sorted(provenance, key=lambda item: item.to_dict().__repr__())),
        )
        object.__setattr__(self, "reason_codes", reason_codes)

    def requirements_for_stage(
        self, stage: RequirementStage
    ) -> tuple[ProgramRequirement, ...]:
        """Return requirements applicable to ``stage``.

        Metadata-only definitions have unknown applicability and remain in the
        result so an audit cannot silently ignore a governed requirement.
        """

        if not isinstance(stage, RequirementStage):
            raise TypeError("stage must be a RequirementStage")
        return tuple(
            requirement
            for requirement in self.requirements
            if requirement_stage(requirement.definition) in (stage, None)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "regulation": self.regulation.value,
            "program": str(self.program),
            "status": self.status.value,
            "dataset_version": (
                self.dataset_version.to_dict() if self.dataset_version else None
            ),
            "reason_codes": [reason.value for reason in self.reason_codes],
            "provenance": [item.to_dict() for item in self.provenance],
            "requirements": [item.to_dict() for item in self.requirements],
        }


def requirement_stage(
    definition: RequirementDefinition | None,
) -> RequirementStage | None:
    """Return a definition's explicit stage, or ``None`` when unknown."""

    if definition is None:
        return None
    if isinstance(
        definition, (EarnedCreditThresholdRequirement, TotalProgramCreditsRequirement)
    ):
        return definition.stage
    return RequirementStage.PROGRAM_COMPLETION


def _validate_number(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _validate_nonnegative_number(value: object, name: str) -> None:
    _validate_number(value, name)
    if value < 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be non-negative")


def _validate_optional_nonnegative_number(
    value: object,
    name: str,
) -> None:
    if value is not None:
        _validate_nonnegative_number(value, name)


def _validate_definition_scope(
    definition: RequirementDefinition,
    regulation: Regulation,
    program: Program,
) -> None:
    scoped_values: list[tuple[Regulation, Program]] = []
    if isinstance(
        definition, (CourseCompletionRequirement, ZeroCreditCourseRequirement)
    ):
        scoped_values.append((definition.course.regulation, definition.course.program))
    elif isinstance(definition, CourseCountFromPoolRequirement):
        scoped_values.append(
            (definition.pool_id.regulation, definition.pool_id.program)
        )
    elif isinstance(definition, ConcentrationRequirement):
        scoped_values.append(
            (
                definition.technical_pool_id.regulation,
                definition.technical_pool_id.program,
            )
        )
        scoped_values.extend(
            (item.regulation, item.program) for item in definition.concentrations
        )
    elif isinstance(definition, ElectiveSlotRequirement):
        scoped_values.append(
            (definition.slot_id.regulation, definition.slot_id.program)
        )
        if definition.pool_id is not None:
            scoped_values.append(
                (definition.pool_id.regulation, definition.pool_id.program)
            )
    if any(item != (regulation, program) for item in scoped_values):
        raise ValueError("requirement definition scope must match its governed record")
