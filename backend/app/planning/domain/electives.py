"""Scoped elective identities and pool metadata.

Elective slots and pools are requirements-domain entities, never courses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from .course import CourseIdentity, Program, Regulation
from .lifecycle import ApprovalStatus, VerificationStatus
from .provenance import Provenance


@dataclass(frozen=True, slots=True)
class _ScopedRequirementId:
    regulation: Regulation
    program: Program
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(self.program, Program):
            raise TypeError("program must be a Program")
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("value must be a non-empty string")

    @property
    def identifier(self) -> str:
        return f"{self.regulation.value}:{self.program}:{self.value}"

    def __str__(self) -> str:
        return self.identifier


@dataclass(frozen=True, slots=True)
class ElectivePoolId(_ScopedRequirementId):
    """Stable scoped identity for an elective pool."""


@dataclass(frozen=True, slots=True)
class ElectiveSlotId(_ScopedRequirementId):
    """Stable scoped identity for an elective requirement slot."""


@dataclass(frozen=True, slots=True)
class ConcentrationId(_ScopedRequirementId):
    """Stable scoped identity for a concentration family."""


class ElectivePoolType(StrEnum):
    CONCENTRATION = "CONCENTRATION"
    PROGRAM_TECHNICAL_ELECTIVES = "PROGRAM_TECHNICAL_ELECTIVES"
    UNIVERSITY_ELECTIVE = "UNIVERSITY_ELECTIVE"


@dataclass(frozen=True, slots=True)
class ElectivePool:
    """Governed set of real courses that may satisfy a selection rule."""

    pool_id: ElectivePoolId
    pool_name: str
    pool_type: ElectivePoolType
    allowed_courses: tuple[CourseIdentity, ...] = ()
    allowed_external_codes: tuple[str, ...] = ()
    required_course_count: int | None = None
    required_credit_hours: int | float | None = None
    approval_status: ApprovalStatus = ApprovalStatus.SOURCE_VERIFIED
    verification_status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.pool_id, ElectivePoolId):
            raise TypeError("pool_id must be an ElectivePoolId")
        if not isinstance(self.pool_name, str) or not self.pool_name.strip():
            raise ValueError("pool_name must be non-empty")
        if not isinstance(self.pool_type, ElectivePoolType):
            raise TypeError("pool_type must be an ElectivePoolType")
        courses = tuple(self.allowed_courses)
        if not all(isinstance(course, CourseIdentity) for course in courses):
            raise TypeError("allowed_courses must contain CourseIdentity values")
        if any(
            course.regulation is not self.pool_id.regulation
            or course.program != self.pool_id.program
            for course in courses
        ):
            raise ValueError("allowed course scope must match pool scope")
        if len(courses) != len(set(courses)):
            raise ValueError("allowed_courses must not contain duplicates")
        external_codes = tuple(self.allowed_external_codes)
        if not all(isinstance(code, str) and code.strip() for code in external_codes):
            raise ValueError("allowed_external_codes must contain non-empty strings")
        if len(external_codes) != len(set(external_codes)):
            raise ValueError("allowed_external_codes must not contain duplicates")
        if self.required_course_count is not None and (
            isinstance(self.required_course_count, bool)
            or not isinstance(self.required_course_count, int)
            or self.required_course_count < 0
        ):
            raise ValueError("required_course_count must be a non-negative integer")
        if self.required_credit_hours is not None and (
            isinstance(self.required_credit_hours, bool)
            or not isinstance(self.required_credit_hours, (int, float))
            or self.required_credit_hours < 0
            or not math.isfinite(self.required_credit_hours)
        ):
            raise ValueError("required_credit_hours must be non-negative numeric")
        if not isinstance(self.approval_status, ApprovalStatus):
            raise TypeError("approval_status must be an ApprovalStatus")
        if not isinstance(self.verification_status, VerificationStatus):
            raise TypeError("verification_status must be a VerificationStatus")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")
        object.__setattr__(
            self,
            "allowed_courses",
            tuple(sorted(courses, key=lambda course: course.course_id)),
        )
        object.__setattr__(
            self, "allowed_external_codes", tuple(sorted(external_codes))
        )


@dataclass(frozen=True, slots=True)
class Concentration:
    """Named concentration family, separate from CourseIdentity."""

    concentration_id: ConcentrationId
    name: str
    allowed_courses: tuple[CourseIdentity, ...] = ()
    approval_status: ApprovalStatus = ApprovalStatus.SOURCE_VERIFIED
    verification_status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.concentration_id, ConcentrationId):
            raise TypeError("concentration_id must be a ConcentrationId")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be non-empty")
        courses = tuple(self.allowed_courses)
        if not all(isinstance(course, CourseIdentity) for course in courses):
            raise TypeError("allowed_courses must contain CourseIdentity values")
        if any(
            course.regulation is not self.concentration_id.regulation
            or course.program != self.concentration_id.program
            for course in courses
        ):
            raise ValueError("allowed course scope must match concentration scope")
        if not isinstance(self.approval_status, ApprovalStatus):
            raise TypeError("approval_status must be an ApprovalStatus")
        if not isinstance(self.verification_status, VerificationStatus):
            raise TypeError("verification_status must be a VerificationStatus")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")
        object.__setattr__(
            self,
            "allowed_courses",
            tuple(sorted(courses, key=lambda course: course.course_id)),
        )
