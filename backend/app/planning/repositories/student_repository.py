"""Repository boundary for student state."""

from typing import Protocol, runtime_checkable

from ..domain.student import StudentState


class StudentRepositoryError(RuntimeError):
    """Base error for safe failures while resolving trusted student state."""


@runtime_checkable
class StudentRepository(Protocol):
    """Read-only domain contract for student-state retrieval."""

    def get_student_state(self, student_id: str) -> StudentState | None:
        """Return the current planning input for a student, if it exists."""

        ...
