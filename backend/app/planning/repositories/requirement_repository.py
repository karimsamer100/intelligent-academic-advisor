"""Repository boundary for program requirements."""

from typing import Protocol, runtime_checkable

from ..domain.course import Program, Regulation
from ..domain.electives import ElectivePool
from ..domain.requirements import (
    ProgramRequirement,
    ProgramRequirementSet,
    RequirementStage,
)


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

    def list_elective_pools(
        self,
        *,
        regulation: Regulation,
        program: Program,
    ) -> tuple[ElectivePool, ...]:
        """Return scoped elective pools without exposing source-file fields."""

        ...

    def get_requirement_set(
        self,
        *,
        regulation: Regulation,
        program: Program,
        stage: RequirementStage | None = None,
    ) -> ProgramRequirementSet:
        """Return requirements with explicit coverage metadata.

        ``list_requirements`` remains available for compatibility, but an
        audit must use this contract when it needs to reason about completeness.
        """

        ...
