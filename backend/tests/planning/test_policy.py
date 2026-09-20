import pytest

from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.reasons import ReasonCode
from app.planning.policy import ExecutionMode, ExecutionPolicy, PolicyDecision


def test_authoritative_policy_accepts_approved_source_verified_critical_data() -> None:
    decision = ExecutionPolicy(ExecutionMode.AUTHORITATIVE).assess(
        ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        critical=True,
    )

    assert decision.allowed is True
    assert decision.authoritative is True
    assert decision.requires_human_review is False
    assert decision.reason_codes == ()


def test_authoritative_policy_rejects_unapproved_critical_data() -> None:
    decision = ExecutionPolicy(ExecutionMode.AUTHORITATIVE).assess(
        ApprovalStatus.SOURCE_VERIFIED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        critical=True,
    )

    assert decision.allowed is False
    assert decision.authoritative is False
    assert decision.requires_human_review is True
    assert ReasonCode.UNAPPROVED_RULE in decision.reason_codes


@pytest.mark.parametrize(
    "status, reason",
    [
        (ApprovalStatus.BLOCKED, ReasonCode.BLOCKED_RULE),
        (ApprovalStatus.CONFLICTED, ReasonCode.CONFLICTED_RULE),
    ],
)
@pytest.mark.parametrize("mode", list(ExecutionMode))
def test_blocked_and_conflicted_data_fail_closed_in_both_modes(
    mode: ExecutionMode,
    status: ApprovalStatus,
    reason: ReasonCode,
) -> None:
    decision = ExecutionPolicy(mode).assess(
        status,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        critical=True,
    )

    assert decision.allowed is False
    assert decision.authoritative is False
    assert decision.requires_human_review is True
    assert reason in decision.reason_codes


def test_development_policy_can_exercise_unapproved_data_without_authority() -> None:
    decision = ExecutionPolicy(ExecutionMode.DEVELOPMENT).assess(
        ApprovalStatus.SOURCE_VERIFIED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        critical=True,
    )

    assert decision.allowed is True
    assert decision.authoritative is False
    assert decision.requires_human_review is False
    assert ReasonCode.UNAPPROVED_RULE in decision.reason_codes


def test_missing_verification_is_unsafe_for_authoritative_critical_data() -> None:
    decision = ExecutionPolicy(ExecutionMode.AUTHORITATIVE).assess(
        ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.NEEDS_VERIFICATION,
        critical=True,
    )

    assert decision.allowed is False
    assert decision.requires_human_review is True
    assert ReasonCode.UNVERIFIED_RULE in decision.reason_codes


def test_policy_contracts_reject_untyped_state() -> None:
    with pytest.raises(TypeError):
        ExecutionPolicy("AUTHORITATIVE")  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        PolicyDecision(
            mode=ExecutionMode.AUTHORITATIVE,
            approval_status="APPROVED",  # type: ignore[arg-type]
            verification_status=VerificationStatus.SOURCE_VERIFIED,
            critical=True,
            allowed=True,
            authoritative=True,
            requires_human_review=False,
        )


def test_policy_decision_cannot_mark_unapproved_data_authoritative() -> None:
    with pytest.raises(ValueError):
        PolicyDecision(
            mode=ExecutionMode.AUTHORITATIVE,
            approval_status=ApprovalStatus.SOURCE_VERIFIED,
            verification_status=VerificationStatus.SOURCE_VERIFIED,
            critical=True,
            allowed=True,
            authoritative=True,
            requires_human_review=False,
        )
