"""Execution safety policy for academic-data-dependent operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .domain.lifecycle import ApprovalStatus, VerificationStatus
from .domain.reasons import ReasonCode


class ExecutionMode(StrEnum):
    """Whether an operation is allowed to produce authoritative decisions."""

    AUTHORITATIVE = "AUTHORITATIVE"
    DEVELOPMENT = "DEVELOPMENT"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Structured safety result; academic uncertainty is not an exception."""

    mode: ExecutionMode
    approval_status: ApprovalStatus
    verification_status: VerificationStatus | None
    critical: bool
    allowed: bool
    authoritative: bool
    requires_human_review: bool
    reason_codes: tuple[ReasonCode, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ExecutionMode):
            raise TypeError("mode must be an ExecutionMode")
        if not isinstance(self.approval_status, ApprovalStatus):
            raise TypeError("approval_status must be an ApprovalStatus")
        if self.verification_status is not None and not isinstance(
            self.verification_status, VerificationStatus
        ):
            raise TypeError("verification_status must be a VerificationStatus or None")
        for name in ("critical", "allowed", "authoritative", "requires_human_review"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool")
        normalized_reasons = tuple(self.reason_codes)
        if not all(isinstance(reason, ReasonCode) for reason in normalized_reasons):
            raise TypeError("reason_codes must contain only ReasonCode values")
        object.__setattr__(self, "reason_codes", normalized_reasons)
        if self.authoritative and self.mode is not ExecutionMode.AUTHORITATIVE:
            raise ValueError("Development decisions cannot be authoritative")
        if self.authoritative and not self.allowed:
            raise ValueError("A denied decision cannot be authoritative")
        if self.authoritative and self.requires_human_review:
            raise ValueError("A human-review decision cannot be authoritative")
        if self.authoritative and self.approval_status is not ApprovalStatus.APPROVED:
            raise ValueError("Only approved data can be authoritative")
        if (
            self.authoritative
            and self.critical
            and (self.verification_status is not VerificationStatus.SOURCE_VERIFIED)
        ):
            raise ValueError("Critical authoritative data must be source-verified")

    @property
    def can_evaluate(self) -> bool:
        """Compatibility name for callers that describe policy as evaluation."""

        return self.allowed

    @property
    def safe_for_authoritative_decision(self) -> bool:
        return self.allowed and self.authoritative


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Centralized policy for approval-aware engine execution."""

    mode: ExecutionMode

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ExecutionMode):
            raise TypeError("mode must be an ExecutionMode")

    @classmethod
    def authoritative(cls) -> "ExecutionPolicy":
        return cls(ExecutionMode.AUTHORITATIVE)

    @classmethod
    def development(cls) -> "ExecutionPolicy":
        return cls(ExecutionMode.DEVELOPMENT)

    def assess(
        self,
        approval_status: ApprovalStatus,
        *,
        verification_status: VerificationStatus | None = None,
        critical: bool = True,
    ) -> PolicyDecision:
        """Assess whether a data-dependent operation may proceed.

        Approval is the primary academic safety state.  Verification is kept
        separate and is required for critical authoritative data, so a record
        can remain visibly source-verified without being treated as approved.
        """

        if not isinstance(approval_status, ApprovalStatus):
            raise TypeError("approval_status must be an ApprovalStatus")
        if verification_status is not None and not isinstance(
            verification_status, VerificationStatus
        ):
            raise TypeError("verification_status must be a VerificationStatus or None")
        if not isinstance(critical, bool):
            raise TypeError("critical must be a bool")

        reasons = self._reason_codes(approval_status, verification_status)
        unsafe_state = approval_status in {
            ApprovalStatus.BLOCKED,
            ApprovalStatus.CONFLICTED,
            ApprovalStatus.SUPERSEDED,
        }
        approved_and_verified = (
            approval_status is ApprovalStatus.APPROVED
            and verification_status is VerificationStatus.SOURCE_VERIFIED
        )

        if unsafe_state:
            return PolicyDecision(
                mode=self.mode,
                approval_status=approval_status,
                verification_status=verification_status,
                critical=critical,
                allowed=False,
                authoritative=False,
                requires_human_review=True,
                reason_codes=reasons,
            )

        if self.mode is ExecutionMode.AUTHORITATIVE:
            if critical and not approved_and_verified:
                return PolicyDecision(
                    mode=self.mode,
                    approval_status=approval_status,
                    verification_status=verification_status,
                    critical=critical,
                    allowed=False,
                    authoritative=False,
                    requires_human_review=True,
                    reason_codes=reasons,
                )
            if not critical and approval_status is not ApprovalStatus.APPROVED:
                return PolicyDecision(
                    mode=self.mode,
                    approval_status=approval_status,
                    verification_status=verification_status,
                    critical=critical,
                    allowed=True,
                    authoritative=False,
                    requires_human_review=False,
                    reason_codes=reasons,
                )
            return PolicyDecision(
                mode=self.mode,
                approval_status=approval_status,
                verification_status=verification_status,
                critical=critical,
                allowed=True,
                authoritative=True,
                requires_human_review=False,
                reason_codes=(),
            )

        return PolicyDecision(
            mode=self.mode,
            approval_status=approval_status,
            verification_status=verification_status,
            critical=critical,
            allowed=True,
            authoritative=False,
            requires_human_review=False,
            reason_codes=reasons,
        )

    def evaluate(
        self,
        approval_status: ApprovalStatus,
        *,
        verification_status: VerificationStatus | None = None,
        critical: bool = True,
    ) -> PolicyDecision:
        """Alias for callers that use evaluation terminology."""

        return self.assess(
            approval_status,
            verification_status=verification_status,
            critical=critical,
        )

    @staticmethod
    def _reason_codes(
        approval_status: ApprovalStatus,
        verification_status: VerificationStatus | None,
    ) -> tuple[ReasonCode, ...]:
        if approval_status is ApprovalStatus.BLOCKED:
            reasons = [ReasonCode.BLOCKED_RULE]
        elif approval_status is ApprovalStatus.CONFLICTED:
            reasons = [ReasonCode.CONFLICTED_RULE]
        elif approval_status is ApprovalStatus.SUPERSEDED:
            reasons = [ReasonCode.UNAPPROVED_RULE]
        elif approval_status is not ApprovalStatus.APPROVED:
            reasons = [ReasonCode.UNAPPROVED_RULE]
        else:
            reasons = []

        if verification_status is not VerificationStatus.SOURCE_VERIFIED:
            reasons.append(ReasonCode.UNVERIFIED_RULE)
        return tuple(dict.fromkeys(reasons))
