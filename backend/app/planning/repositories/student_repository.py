"""Repository boundary for student state."""

from typing import Protocol, runtime_checkable

from ..domain.student import StudentState


@runtime_checkable
class StudentRepository(Protocol):
    """Read-only domain contract for student-state retrieval."""

    def get_student_state(self, student_id: str) -> StudentState | None:
        """Return the current planning input for a student, if it exists."""

        ...
