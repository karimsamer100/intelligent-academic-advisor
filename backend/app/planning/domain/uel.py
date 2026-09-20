"""Typed UEL progress and ASU-to-UEL mapping contracts.

UEL modules are an external academic progression context.  They are related
to ASU courses through governed mappings, but neither side is a replacement
for the other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .course import CourseIdentity, Regulation
from .provenance import Provenance
from .reasons import ReasonCode
from .results import ResultMetadata
from .student import StudentState
from .trace import DecisionTrace


_UEL_MODULE_ID = re.compile(r"^R(?P<regulation>18|23):UEL:(?P<code>[A-Z][A-Z0-9_-]*)$")


class UELProgressCoverage(StrEnum):
    """Coverage of UEL facts or mapping records."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


# A short compatibility name for callers that use the generic coverage term.
UELCoverageStatus = UELProgressCoverage


class UELModuleStatus(StrEnum):
    """Explicit status of one UEL module."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    IN_PROGRESS = "IN_PROGRESS"
    OUTSTANDING = "OUTSTANDING"
    UNKNOWN = "UNKNOWN"


class UELRiskLevel(StrEnum):
    """Structured progression signal, not an ASU eligibility decision."""

    NONE = "NONE"
    ATTENTION = "ATTENTION"
    PROGRESSION_RISK = "PROGRESSION_RISK"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class UELModuleId:
    """Regulation-scoped identity for a UEL module."""

    regulation: Regulation
    module_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(self.module_code, str) or not re.fullmatch(
            r"[A-Z][A-Z0-9_-]*", self.module_code
        ):
            raise ValueError(f"Invalid UEL module code: {self.module_code!r}")

    @classmethod
    def parse(cls, value: str) -> "UELModuleId":
        if not isinstance(value, str):
            raise ValueError(f"UEL module identity must be a string: {value!r}")
        match = _UEL_MODULE_ID.fullmatch(value)
        if match is None:
            raise ValueError(f"Malformed UEL module identity: {value!r}")
        return cls(Regulation(f"R{match['regulation']}"), match["code"])

    @property
    def module_id(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.regulation}:UEL:{self.module_code}"


@dataclass(frozen=True, slots=True)
class UELModuleDefinition:
    """Governed catalog metadata for a UEL module."""

    module: UELModuleId
    module_name: str
    credits: int | float
    provenance: Provenance

    def __post_init__(self) -> None:
        if not isinstance(self.module, UELModuleId):
            raise TypeError("module must be a UELModuleId")
        if not isinstance(self.module_name, str) or not self.module_name.strip():
            raise ValueError("module_name must be a non-empty string")
        if isinstance(self.credits, bool) or not isinstance(self.credits, (int, float)):
            raise TypeError("credits must be numeric")
        if self.credits < 0:
            raise ValueError("credits cannot be negative")
        if not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance")

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module.module_id,
            "module_name": self.module_name,
            "credits": self.credits,
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class UELModuleResult:
    """One explicit UEL result; no ASU grade inference is performed."""

    module: UELModuleId
    status: UELModuleStatus
    provenance: Provenance | None = None
    explicit_result: bool = True
    requires_human_review: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.module, UELModuleId):
            raise TypeError("module must be a UELModuleId")
        if not isinstance(self.status, UELModuleStatus):
            raise TypeError("status must be a UELModuleStatus")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")
        if not isinstance(self.explicit_result, bool):
            raise TypeError("explicit_result must be a bool")
        if not isinstance(self.requires_human_review, bool):
            raise TypeError("requires_human_review must be a bool")
        if not self.explicit_result and self.status not in {
            UELModuleStatus.OUTSTANDING,
            UELModuleStatus.UNKNOWN,
        }:
            raise ValueError("implicit UEL results may only be outstanding or unknown")

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module.module_id,
            "status": self.status.value,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "explicit_result": self.explicit_result,
            "requires_human_review": self.requires_human_review,
        }


@dataclass(frozen=True, slots=True)
class UELStudentProgress:
    """Separate UEL student facts with explicit absence coverage."""

    module_results: tuple[UELModuleResult, ...] = ()
    known_modules: tuple[UELModuleId, ...] = ()
    coverage: UELProgressCoverage = UELProgressCoverage.UNAVAILABLE

    def __post_init__(self) -> None:
        results = tuple(self.module_results)
        known = tuple(self.known_modules)
        if not all(isinstance(item, UELModuleResult) for item in results):
            raise TypeError("module_results must contain UELModuleResult values")
        if not all(isinstance(item, UELModuleId) for item in known):
            raise TypeError("known_modules must contain UELModuleId values")
        if len({item.module for item in results}) != len(results):
            raise ValueError("module_results must have unique modules")
        if not isinstance(self.coverage, UELProgressCoverage):
            raise TypeError("coverage must be a UELProgressCoverage")
        object.__setattr__(
            self,
            "module_results",
            tuple(sorted(results, key=lambda item: item.module.module_id)),
        )
        object.__setattr__(self, "known_modules", tuple(sorted(set(known), key=str)))

    @property
    def module_ids(self) -> tuple[UELModuleId, ...]:
        return tuple(
            sorted(
                {item.module for item in self.module_results} | set(self.known_modules),
                key=str,
            )
        )

    def result_for(self, module: UELModuleId) -> UELModuleResult | None:
        if not isinstance(module, UELModuleId):
            raise TypeError("module must be a UELModuleId")
        result = next(
            (item for item in self.module_results if item.module == module), None
        )
        if result is not None:
            return result
        if (
            module in self.known_modules
            and self.coverage is UELProgressCoverage.COMPLETE
        ):
            return UELModuleResult(
                module=module,
                status=UELModuleStatus.OUTSTANDING,
                explicit_result=False,
            )
        return None

    @property
    def passed_modules(self) -> tuple[UELModuleId, ...]:
        return self._modules_with_status(UELModuleStatus.PASSED)

    @property
    def failed_modules(self) -> tuple[UELModuleId, ...]:
        return self._modules_with_status(UELModuleStatus.FAILED)

    @property
    def in_progress_modules(self) -> tuple[UELModuleId, ...]:
        return self._modules_with_status(UELModuleStatus.IN_PROGRESS)

    @property
    def outstanding_modules(self) -> tuple[UELModuleId, ...]:
        return self._modules_with_status(UELModuleStatus.OUTSTANDING)

    @property
    def unknown_modules(self) -> tuple[UELModuleId, ...]:
        return tuple(
            module
            for module in self.module_ids
            if self.result_for(module) is None
            or self.result_for(module).status is UELModuleStatus.UNKNOWN
        )

    def _modules_with_status(self, status: UELModuleStatus) -> tuple[UELModuleId, ...]:
        return tuple(
            module
            for module in self.module_ids
            if (result := self.result_for(module)) is not None
            and result.status is status
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "coverage": self.coverage.value,
            "known_modules": [item.module_id for item in self.known_modules],
            "module_results": [item.to_dict() for item in self.module_results],
            "passed_modules": [item.module_id for item in self.passed_modules],
            "failed_modules": [item.module_id for item in self.failed_modules],
            "in_progress_modules": [
                item.module_id for item in self.in_progress_modules
            ],
            "outstanding_modules": [
                item.module_id for item in self.outstanding_modules
            ],
            "unknown_modules": [item.module_id for item in self.unknown_modules],
        }


@dataclass(frozen=True, slots=True)
class UELMapping:
    """Governed relationship between one ASU course and one UEL module."""

    mapping_id: str
    module: UELModuleId
    course: CourseIdentity
    mapping_type: str
    weight_percent: int | float | None = None
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mapping_id, str) or not self.mapping_id.strip():
            raise ValueError("mapping_id must be a non-empty string")
        if not isinstance(self.module, UELModuleId):
            raise TypeError("module must be a UELModuleId")
        if not isinstance(self.course, CourseIdentity):
            raise TypeError("course must be a CourseIdentity")
        if self.module.regulation is not self.course.regulation:
            raise ValueError("module and course regulations must match")
        if not isinstance(self.mapping_type, str) or not self.mapping_type.strip():
            raise ValueError("mapping_type must be a non-empty string")
        if self.weight_percent is not None:
            if isinstance(self.weight_percent, bool) or not isinstance(
                self.weight_percent, (int, float)
            ):
                raise TypeError("weight_percent must be numeric or None")
            if not 0 <= self.weight_percent <= 100:
                raise ValueError("weight_percent must be between 0 and 100")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")

    def to_dict(self) -> dict[str, object]:
        return {
            "mapping_id": self.mapping_id,
            "module": self.module.module_id,
            "course": self.course.course_id,
            "mapping_type": self.mapping_type,
            "weight_percent": self.weight_percent,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


@dataclass(frozen=True, slots=True)
class UELMappingSet:
    """Deterministic forward/reverse index over UEL mappings."""

    mappings: tuple[UELMapping, ...] = ()
    coverage: UELProgressCoverage = UELProgressCoverage.UNAVAILABLE
    modules: tuple[UELModuleDefinition, ...] = ()

    def __post_init__(self) -> None:
        mappings = tuple(self.mappings)
        modules = tuple(self.modules)
        if not all(isinstance(item, UELMapping) for item in mappings):
            raise TypeError("mappings must contain UELMapping values")
        if len({item.mapping_id for item in mappings}) != len(mappings):
            raise ValueError("mappings must have unique mapping IDs")
        if not all(isinstance(item, UELModuleDefinition) for item in modules):
            raise TypeError("modules must contain UELModuleDefinition values")
        if len({item.module for item in modules}) != len(modules):
            raise ValueError("modules must have unique module identities")
        if not isinstance(self.coverage, UELProgressCoverage):
            raise TypeError("coverage must be a UELProgressCoverage")
        object.__setattr__(
            self,
            "mappings",
            tuple(sorted(mappings, key=lambda item: item.mapping_id)),
        )
        object.__setattr__(
            self, "modules", tuple(sorted(modules, key=lambda item: str(item.module)))
        )

    def mappings_for_module(self, module: UELModuleId) -> tuple[UELMapping, ...]:
        return tuple(item for item in self.mappings if item.module == module)

    def mappings_for_course(self, course: CourseIdentity) -> tuple[UELMapping, ...]:
        return tuple(item for item in self.mappings if item.course == course)

    def courses_for_module(self, module: UELModuleId) -> tuple[CourseIdentity, ...]:
        return tuple(
            sorted({item.course for item in self.mappings_for_module(module)}, key=str)
        )

    def modules_for_course(self, course: CourseIdentity) -> tuple[UELModuleId, ...]:
        return tuple(
            sorted({item.module for item in self.mappings_for_course(course)}, key=str)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "coverage": self.coverage.value,
            "mappings": [item.to_dict() for item in self.mappings],
            "modules": [item.to_dict() for item in self.modules],
        }


@dataclass(frozen=True, slots=True)
class UELCoverage:
    mapping: UELProgressCoverage
    module_facts: UELProgressCoverage
    evaluation: UELProgressCoverage

    def __post_init__(self) -> None:
        for name in ("mapping", "module_facts", "evaluation"):
            if not isinstance(getattr(self, name), UELProgressCoverage):
                raise TypeError(f"{name} must be a UELProgressCoverage")

    @property
    def overall(self) -> UELProgressCoverage:
        values = (self.mapping, self.module_facts, self.evaluation)
        if all(item is UELProgressCoverage.UNAVAILABLE for item in values):
            return UELProgressCoverage.UNAVAILABLE
        if any(item is not UELProgressCoverage.COMPLETE for item in values):
            return UELProgressCoverage.PARTIAL
        return UELProgressCoverage.COMPLETE

    def to_dict(self) -> dict[str, object]:
        return {
            "mapping": self.mapping.value,
            "module_facts": self.module_facts.value,
            "evaluation": self.evaluation.value,
            "overall": self.overall.value,
        }


@dataclass(frozen=True, slots=True)
class UELProgressionRisk:
    module: UELModuleId
    level: UELRiskLevel
    mapped_courses: tuple[CourseIdentity, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    provenance: tuple[Provenance, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.module, UELModuleId):
            raise TypeError("module must be a UELModuleId")
        if not isinstance(self.level, UELRiskLevel):
            raise TypeError("level must be a UELRiskLevel")
        courses = tuple(self.mapped_courses)
        if not all(isinstance(item, CourseIdentity) for item in courses):
            raise TypeError("mapped_courses must contain CourseIdentity values")
        if not all(isinstance(item, Provenance) for item in self.provenance):
            raise TypeError("provenance must contain Provenance values")
        if not all(isinstance(item, ReasonCode) for item in self.reason_codes):
            raise TypeError("reason_codes must contain ReasonCode values")
        object.__setattr__(self, "mapped_courses", tuple(sorted(set(courses), key=str)))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "provenance", tuple(self.provenance))

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module.module_id,
            "level": self.level.value,
            "mapped_courses": [item.course_id for item in self.mapped_courses],
            "reason_codes": [item.value for item in self.reason_codes],
            "provenance": [item.to_dict() for item in self.provenance],
        }


@dataclass(frozen=True, slots=True)
class UELRiskDelta:
    """Typed before/after change for one UEL module's risk signal."""

    module: UELModuleId
    baseline: UELRiskLevel
    scenario: UELRiskLevel

    def __post_init__(self) -> None:
        if not isinstance(self.module, UELModuleId):
            raise TypeError("module must be a UELModuleId")
        if not isinstance(self.baseline, UELRiskLevel) or not isinstance(
            self.scenario, UELRiskLevel
        ):
            raise TypeError("baseline and scenario must be UELRiskLevel values")

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module.module_id,
            "baseline": self.baseline.value,
            "scenario": self.scenario.value,
        }


@dataclass(frozen=True, slots=True)
class UELProgressEvaluationResult:
    progress: UELStudentProgress
    mappings: UELMappingSet
    coverage: UELCoverage
    risks: tuple[UELProgressionRisk, ...]
    metadata: ResultMetadata
    trace: DecisionTrace

    def __post_init__(self) -> None:
        if not isinstance(self.progress, UELStudentProgress):
            raise TypeError("progress must be a UELStudentProgress")
        if not isinstance(self.mappings, UELMappingSet):
            raise TypeError("mappings must be a UELMappingSet")
        if not isinstance(self.coverage, UELCoverage):
            raise TypeError("coverage must be a UELCoverage")
        if not isinstance(self.metadata, ResultMetadata):
            raise TypeError("metadata must be a ResultMetadata")
        if not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace")
        risks = tuple(self.risks)
        if not all(isinstance(item, UELProgressionRisk) for item in risks):
            raise TypeError("risks must contain UELProgressionRisk values")
        object.__setattr__(
            self,
            "risks",
            tuple(sorted(risks, key=lambda item: item.module.module_id)),
        )

    @property
    def mapped_courses(self) -> tuple[CourseIdentity, ...]:
        return tuple(sorted({item.course for item in self.mappings.mappings}, key=str))

    def risk_for(self, module: UELModuleId) -> UELProgressionRisk | None:
        return next((item for item in self.risks if item.module == module), None)

    def to_dict(self) -> dict[str, object]:
        return {
            "progress": self.progress.to_dict(),
            "mappings": self.mappings.to_dict(),
            "coverage": self.coverage.to_dict(),
            "risks": [item.to_dict() for item in self.risks],
            "metadata": self.metadata.to_dict(),
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class UELProgressRequest:
    """Typed input bundle for facade/API boundaries."""

    student: StudentState | None
    progress: UELStudentProgress
    mappings: UELMappingSet

    def __post_init__(self) -> None:
        if self.student is not None and not isinstance(self.student, StudentState):
            raise TypeError("student must be a StudentState or None")
        if not isinstance(self.progress, UELStudentProgress):
            raise TypeError("progress must be a UELStudentProgress")
        if not isinstance(self.mappings, UELMappingSet):
            raise TypeError("mappings must be a UELMappingSet")

    def to_dict(self) -> dict[str, object]:
        return {
            "student_id": self.student.student_id if self.student else None,
            "progress": self.progress.to_dict(),
            "mappings": self.mappings.to_dict(),
        }


__all__ = [
    "UELCoverage",
    "UELCoverageStatus",
    "UELMapping",
    "UELMappingSet",
    "UELModuleDefinition",
    "UELModuleId",
    "UELModuleResult",
    "UELModuleStatus",
    "UELProgressCoverage",
    "UELProgressEvaluationResult",
    "UELProgressRequest",
    "UELProgressionRisk",
    "UELRiskDelta",
    "UELRiskLevel",
    "UELStudentProgress",
]
