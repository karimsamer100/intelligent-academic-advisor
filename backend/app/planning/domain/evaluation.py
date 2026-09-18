"""Typed outcomes and results for deterministic rule evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .lifecycle import ApprovalStatus, VerificationStatus
from .provenance import Provenance
from .reasons import ReasonCode
from .results import ResultMetadata
from .trace import DecisionTrace


class EvaluationOutcome(StrEnum):
    """Three-valued outcome of evaluating a structured academic expression."""

    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True, slots=True)
class RuleEvaluationResult:
    """Evaluation outcome plus the shared context needed for auditability."""

    rule_id: str
    outcome: EvaluationOutcome
    metadata: ResultMetadata

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str) or not self.rule_id.strip():
            raise ValueError("rule_id must be a non-empty string")
        if not isinstance(self.outcome, EvaluationOutcome):
            raise TypeError("outcome must be an EvaluationOutcome")
        if not isinstance(self.metadata, ResultMetadata):
            raise TypeError("metadata must be a ResultMetadata")
        if self.metadata.decision_trace is None:
            raise ValueError("rule evaluation metadata must include a decision trace")

    @property
    def authoritative(self) -> bool:
        return self.metadata.authoritative

    @property
    def requires_human_review(self) -> bool:
        return self.metadata.requires_human_review

    @property
    def reason_codes(self) -> tuple[ReasonCode, ...]:
        return self.metadata.reason_codes

    @property
    def warnings(self) -> tuple[ReasonCode, ...]:
        return self.metadata.warnings

    @property
    def provenance(self) -> tuple[Provenance, ...]:
        return self.metadata.provenance

    @property
    def decision_trace(self) -> DecisionTrace:
        # The constructor invariant makes this assertion safe and keeps the
        # public result API non-optional for actual evaluations.
        assert self.metadata.decision_trace is not None
        return self.metadata.decision_trace

    @property
    def approval_status(self) -> ApprovalStatus | None:
        return self.metadata.approval_status

    @property
    def verification_status(self) -> VerificationStatus | None:
        return self.metadata.verification_status

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "outcome": self.outcome.value,
            "metadata": self.metadata.to_dict(),
        }
