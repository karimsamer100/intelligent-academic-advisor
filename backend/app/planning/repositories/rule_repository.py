"""Repository boundary for academic rules."""

from typing import Protocol, runtime_checkable

from ..domain.course import Program, Regulation
from ..domain.rules import AcademicRule


@runtime_checkable
class RuleRepository(Protocol):
    """Read-only domain contract for scoped rule retrieval."""

    def get_rule(self, rule_id: str) -> AcademicRule | None:
        """Return one rule by stable rule identifier, if it exists."""

        ...

    def list_rules(
        self,
        *,
        regulation: Regulation,
        program: Program,
    ) -> tuple[AcademicRule, ...]:
        """Return rules for one regulation/program scope."""

        ...
