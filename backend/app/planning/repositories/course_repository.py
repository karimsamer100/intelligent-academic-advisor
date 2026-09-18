"""Repository boundary for course records."""

from typing import Protocol, runtime_checkable

from ..domain.course import Course, CourseIdentity, Program, Regulation


@runtime_checkable
class CourseRepository(Protocol):
    """Read-only domain contract for course lookups.

    Adapters may use PostgreSQL, JSON fixtures, or another source, but the
    engine sees only domain values and canonical identities.
    """

    def get_course(self, course_id: CourseIdentity) -> Course | None:
        """Return one course by canonical identity, if it exists."""

        ...

    def list_courses(
        self,
        *,
        regulation: Regulation,
        program: Program,
    ) -> tuple[Course, ...]:
        """Return courses for one regulation/program scope."""

        ...
