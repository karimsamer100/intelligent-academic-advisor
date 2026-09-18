"""Minimal academic-rule identity records for repository contracts."""

from __future__ import annotations

from dataclasses import dataclass

from .course import Program, Regulation
from .expressions import RuleExpression
from .lifecycle import ApprovalStatus, VerificationStatus
from .provenance import Provenance


@dataclass(frozen=True, slots=True)
class AcademicRule:
    """Governed academic rule metadata and its optional executable expression."""

    rule_id: str
    regulation: Regulation
    program: Program
    approval_status: ApprovalStatus
    verification_status: VerificationStatus
    critical_for_planner: bool = False
    provenance: Provenance | None = None
    expression: RuleExpression | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str) or not self.rule_id.strip():
            raise ValueError("rule_id must be a non-empty string")
        if not isinstance(self.regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(self.program, Program):
            raise TypeError("program must be a Program")
        if not isinstance(self.approval_status, ApprovalStatus):
            raise TypeError("approval_status must be an ApprovalStatus")
        if not isinstance(self.verification_status, VerificationStatus):
            raise TypeError("verification_status must be a VerificationStatus")
        if not isinstance(self.critical_for_planner, bool):
            raise TypeError("critical_for_planner must be a bool")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")
        if self.expression is not None and not isinstance(
            self.expression, RuleExpression
        ):
            raise TypeError("expression must be a RuleExpression or None")
