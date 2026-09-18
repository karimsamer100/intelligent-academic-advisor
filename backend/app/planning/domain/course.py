"""Course identity and regulation value objects.

These types deliberately do not depend on persistence models or course-rule
evaluation.  A course code is only meaningful inside its regulation and
program context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .lifecycle import ApprovalStatus, VerificationStatus


_IDENTITY_TOKEN = re.compile(r"^[A-Z][A-Z0-9_-]*$")
_COURSE_IDENTITY = re.compile(
    r"^R(?P<regulation>18|23):(?P<program>[A-Z][A-Z0-9_-]*):"
    r"(?P<course_code>[A-Z][A-Z0-9_-]*)$"
)


class Regulation(StrEnum):
    """Supported academic regulation identifiers."""

    R18 = "R18"
    R23 = "R23"

    @property
    def year(self) -> int:
        return 2018 if self is Regulation.R18 else 2023

    @classmethod
    def from_year(cls, year: int) -> Regulation:
        try:
            return {2018: cls.R18, 2023: cls.R23}[year]
        except KeyError as error:
            raise ValueError(f"Unsupported regulation year: {year!r}") from error


@dataclass(frozen=True, slots=True)
class Program:
    """Canonical program token used as part of a course identity."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _IDENTITY_TOKEN.fullmatch(self.value):
            raise ValueError(f"Invalid program token: {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CourseIdentity:
    """Regulation-scoped, program-scoped canonical course identity."""

    regulation: Regulation
    program: Program
    course_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(self.program, Program):
            raise TypeError("program must be a Program")
        if not isinstance(self.course_code, str) or not _IDENTITY_TOKEN.fullmatch(
            self.course_code
        ):
            raise ValueError(f"Invalid course code: {self.course_code!r}")

    @classmethod
    def parse(cls, value: str) -> CourseIdentity:
        """Parse a canonical ID such as ``R23:CAIE:CSE341``."""

        if not isinstance(value, str):
            raise ValueError(f"Course identity must be a string: {value!r}")
        match = _COURSE_IDENTITY.fullmatch(value)
        if match is None:
            raise ValueError(f"Malformed course identity: {value!r}")
        return cls(
            regulation=Regulation(f"R{match['regulation']}"),
            program=Program(match["program"]),
            course_code=match["course_code"],
        )

    @property
    def course_id(self) -> str:
        """Return the canonical serialized identity."""

        return str(self)

    def __str__(self) -> str:
        return f"{self.regulation}:{self.program}:{self.course_code}"


@dataclass(frozen=True, slots=True)
class Course:
    """Minimal domain course record for repository boundaries."""

    identity: CourseIdentity
    course_name: str
    credit_hours: int | float
    approval_status: ApprovalStatus
    verification_status: VerificationStatus

    def __post_init__(self) -> None:
        if not isinstance(self.identity, CourseIdentity):
            raise TypeError("identity must be a CourseIdentity")
        if not isinstance(self.course_name, str) or not self.course_name.strip():
            raise ValueError("course_name must be a non-empty string")
        if isinstance(self.credit_hours, bool) or not isinstance(
            self.credit_hours, (int, float)
        ):
            raise TypeError("credit_hours must be numeric")
        if self.credit_hours < 0:
            raise ValueError("credit_hours cannot be negative")
        if not isinstance(self.approval_status, ApprovalStatus):
            raise TypeError("approval_status must be an ApprovalStatus")
        if not isinstance(self.verification_status, VerificationStatus):
            raise TypeError("verification_status must be a VerificationStatus")
