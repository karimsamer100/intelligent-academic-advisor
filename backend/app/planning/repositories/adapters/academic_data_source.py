"""Narrow typed source boundary consumed by eligibility callers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...domain.course import Course, CourseIdentity, Program, Regulation
from ...domain.eligibility import CourseEligibilityRuleSet
from ...domain.version import DatasetVersion
from .academic_data_types import (
    AcademicDataLookup,
    AcademicDataSourceMode,
)


@runtime_checkable
class AcademicEligibilityDataSource(Protocol):
    """Already-loaded course and eligibility data for one source tier.

    Implementations map external records before this boundary.  Eligibility
    services consume the typed lookups and never depend on JSON shape or file
    paths.
    """

    @property
    def source_mode(self) -> AcademicDataSourceMode: ...

    @property
    def dataset_version(self) -> DatasetVersion | None: ...

    def get_course(
        self,
        course_id: CourseIdentity,
    ) -> AcademicDataLookup[Course]: ...

    def list_courses(
        self,
        *,
        regulation: Regulation,
        program: Program,
    ) -> tuple[Course, ...]: ...

    def get_eligibility_rules(
        self,
        course_id: CourseIdentity,
    ) -> AcademicDataLookup[CourseEligibilityRuleSet]: ...
