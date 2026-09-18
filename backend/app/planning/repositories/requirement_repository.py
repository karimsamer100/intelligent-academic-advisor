"""Repository boundary for program requirements."""

from typing import Protocol, runtime_checkable

from ..domain.course import Program, Regulation
from ..domain.requirements import ProgramRequirement


@runtime_checkable
class RequirementRepository(Protocol):
    """Read-only domain contract for scoped requirement retrieval."""

    def list_requirements(
        self,
        *,
        regulation: Regulation,
        program: Program,
    ) -> tuple[ProgramRequirement, ...]:
        """Return requirements for one regulation/program scope."""

        ...
