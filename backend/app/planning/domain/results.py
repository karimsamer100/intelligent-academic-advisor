"""Reusable metadata carried by future Planning Engine result contracts."""

from dataclasses import dataclass

from ..policy import ExecutionMode, PolicyDecision
from .lifecycle import ApprovalStatus, VerificationStatus
from .provenance import Provenance
from .reasons import ReasonCode
from .trace import DecisionTrace
from .version import DatasetVersion


@dataclass(frozen=True, slots=True)
class ResultMetadata:
    """Execution context shared by future engine result types.

    This is deliberately composed into result objects rather than used as a
    common inheritance root. It keeps future result contracts free to model
    their own domain payloads while preserving safety and audit context.
    """

    dataset_version: DatasetVersion
    execution_mode: ExecutionMode
    authoritative: bool
    approval_status: ApprovalStatus | None = None
    verification_status: VerificationStatus | None = None
    engine_version: str | None = None
    ruleset_version: str | None = None
    warnings: tuple[ReasonCode, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    provenance: tuple[Provenance, ...] = ()
    decision_trace: DecisionTrace | None = None
    requires_human_review: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_version, DatasetVersion):
            raise TypeError("dataset_version must be a DatasetVersion")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode")
        if not isinstance(self.authoritative, bool):
            raise TypeError("authoritative must be a bool")
        if not isinstance(self.requires_human_review, bool):
            raise TypeError("requires_human_review must be a bool")
        if self.approval_status is not None and not isinstance(
            self.approval_status, ApprovalStatus
        ):
            raise TypeError("approval_status must be an ApprovalStatus or None")
        if self.verification_status is not None and not isinstance(
            self.verification_status, VerificationStatus
        ):
            raise TypeError("verification_status must be a VerificationStatus or None")
        if (
            self.authoritative
            and self.execution_mode is not ExecutionMode.AUTHORITATIVE
        ):
            raise ValueError("development results cannot be authoritative")
        if self.authoritative and self.requires_human_review:
            raise ValueError("results requiring human review cannot be authoritative")
        if (
            self.authoritative
            and self.approval_status is not None
            and (self.approval_status is not ApprovalStatus.APPROVED)
        ):
            raise ValueError("Only approved data can be represented as authoritative")

        for field_name in ("engine_version", "ruleset_version"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(
                    f"{field_name} must be a non-empty string when provided"
                )

        normalized_warnings = tuple(self.warnings)
        normalized_reasons = tuple(self.reason_codes)
        normalized_provenance = tuple(self.provenance)
        if not all(isinstance(item, ReasonCode) for item in normalized_warnings):
            raise TypeError("warnings must contain only ReasonCode values")
        if not all(isinstance(item, ReasonCode) for item in normalized_reasons):
            raise TypeError("reason_codes must contain only ReasonCode values")
        if not all(isinstance(item, Provenance) for item in normalized_provenance):
            raise TypeError("provenance must contain only Provenance values")
        if self.decision_trace is not None and not isinstance(
            self.decision_trace, DecisionTrace
        ):
            raise TypeError("decision_trace must be a DecisionTrace when provided")
        object.__setattr__(self, "warnings", normalized_warnings)
        object.__setattr__(self, "reason_codes", normalized_reasons)
        object.__setattr__(self, "provenance", normalized_provenance)

    @classmethod
    def from_policy(
        cls,
        dataset_version: DatasetVersion,
        decision: PolicyDecision,
        *,
        engine_version: str | None = None,
        ruleset_version: str | None = None,
        warnings: tuple[ReasonCode, ...] = (),
        provenance: tuple[Provenance, ...] = (),
        decision_trace: DecisionTrace | None = None,
    ) -> "ResultMetadata":
        """Build result context while preserving the policy assessment."""

        if not isinstance(decision, PolicyDecision):
            raise TypeError("decision must be a PolicyDecision")
        return cls(
            dataset_version=dataset_version,
            execution_mode=decision.mode,
            authoritative=decision.authoritative,
            approval_status=decision.approval_status,
            verification_status=decision.verification_status,
            engine_version=engine_version,
            ruleset_version=ruleset_version,
            warnings=warnings,
            reason_codes=decision.reason_codes,
            provenance=provenance,
            decision_trace=decision_trace,
            requires_human_review=decision.requires_human_review,
        )

    @property
    def is_authoritative(self) -> bool:
        """Alias suitable for callers that read metadata as a capability."""

        return self.authoritative

    @property
    def rule_set_version(self) -> str | None:
        """Compatibility alias for callers using ``rule_set`` terminology."""

        return self.ruleset_version

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible, machine-readable representation."""

        return {
            "dataset_version": self.dataset_version.to_dict(),
            "execution_mode": self.execution_mode.value,
            "authoritative": self.authoritative,
            "approval_status": (
                self.approval_status.value if self.approval_status is not None else None
            ),
            "verification_status": (
                self.verification_status.value
                if self.verification_status is not None
                else None
            ),
            "engine_version": self.engine_version,
            "ruleset_version": self.ruleset_version,
            "warnings": [warning.value for warning in self.warnings],
            "reason_codes": [reason.value for reason in self.reason_codes],
            "provenance": [item.to_dict() for item in self.provenance],
            "decision_trace": (
                self.decision_trace.to_dict()
                if self.decision_trace is not None
                else None
            ),
            "requires_human_review": self.requires_human_review,
        }
