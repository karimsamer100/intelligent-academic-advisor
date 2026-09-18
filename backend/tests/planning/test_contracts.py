import pytest

from backend.app.planning.domain.course import CourseIdentity, Program, Regulation
from backend.app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from backend.app.planning.domain.provenance import Provenance
from backend.app.planning.domain.reasons import ReasonCode


def test_valid_canonical_course_identity() -> None:
    identity = CourseIdentity.parse("R23:CAIE:CSE341")

    assert identity.regulation is Regulation.R23
    assert identity.program == Program("CAIE")
    assert identity.course_code == "CSE341"
    assert str(identity) == "R23:CAIE:CSE341"


@pytest.mark.parametrize(
    "raw_identity",
    [
        "",
        "CSE341",
        "R24:CAIE:CSE341",
        "R23:caie:CSE341",
        "R23:CAIE:",
        "R23:CAIE:CSE 341",
        "R23:CAIE:CSE341:EXTRA",
    ],
)
def test_malformed_course_identity_is_rejected(raw_identity: str) -> None:
    with pytest.raises(ValueError):
        CourseIdentity.parse(raw_identity)


def test_regulation_18_and_23_course_identities_are_distinct() -> None:
    regulation_18 = CourseIdentity.parse("R18:CAIE:CSE341")
    regulation_23 = CourseIdentity.parse("R23:CAIE:CSE341")

    assert regulation_18 != regulation_23
    assert regulation_18.regulation is Regulation.R18
    assert regulation_23.regulation is Regulation.R23


def test_lifecycle_keeps_verification_and_approval_separate() -> None:
    assert VerificationStatus.SOURCE_VERIFIED is not ApprovalStatus.APPROVED
    assert (
        VerificationStatus.from_raw("NEEDS_VERIFICATION")
        is VerificationStatus.NEEDS_VERIFICATION
    )
    assert ApprovalStatus.from_raw("BLOCKED") is ApprovalStatus.BLOCKED
    assert ApprovalStatus.from_raw("CONFLICTED") is ApprovalStatus.CONFLICTED


def test_unknown_lifecycle_values_are_rejected() -> None:
    with pytest.raises(ValueError):
        ApprovalStatus.from_raw("MAGICALLY_APPROVED")

    with pytest.raises(ValueError):
        VerificationStatus.from_raw("MAGICALLY_VERIFIED")


def test_provenance_supports_rule_and_source_metadata() -> None:
    provenance = Provenance(
        rule_id="R23-PR-CSE341",
        source_id="SRC-BYLAW-2023",
        source_page=123,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )

    assert provenance.rule_id == "R23-PR-CSE341"
    assert provenance.source_page == 123
    assert provenance.approval_status is ApprovalStatus.APPROVED
    assert provenance.verification_status is VerificationStatus.SOURCE_VERIFIED


def test_provenance_can_be_empty_for_non_rule_derived_results() -> None:
    assert Provenance() == Provenance()


def test_provenance_rejects_invalid_typed_fields() -> None:
    with pytest.raises(TypeError):
        Provenance(approval_status="APPROVED")  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        Provenance(verification_status="SOURCE_VERIFIED")  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        Provenance(source_page=1.5)  # type: ignore[arg-type]


def test_reason_codes_are_machine_readable_and_stable() -> None:
    expected_codes = {
        "MISSING_PREREQUISITE",
        "ALREADY_COMPLETED",
        "CURRENTLY_REGISTERED",
        "WRONG_REGULATION",
        "WRONG_PROGRAM",
        "UNVERIFIED_RULE",
        "UNAPPROVED_RULE",
        "CONFLICTED_RULE",
        "BLOCKED_RULE",
        "MISSING_REQUIRED_DATA",
        "UNSUPPORTED_CASE",
        "EXCEPTION_REQUIRED",
        "AMBIGUOUS_REGULATION",
    }

    assert {code.value for code in ReasonCode} >= expected_codes
