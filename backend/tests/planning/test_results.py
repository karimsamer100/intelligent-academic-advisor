import pytest

from backend.app.planning.domain.course import CourseIdentity
from backend.app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from backend.app.planning.domain.provenance import Provenance
from backend.app.planning.domain.reasons import ReasonCode
from backend.app.planning.domain.results import ResultMetadata
from backend.app.planning.domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceNodeType,
)
from backend.app.planning.domain.version import DatasetVersion
from backend.app.planning.policy import ExecutionMode, ExecutionPolicy


def test_result_metadata_preserves_shared_decision_context() -> None:
    trace = DecisionTrace(
        DecisionTraceNode(
            node_id="eligibility",
            code=TraceCode.ELIGIBILITY,
            node_type=TraceNodeType.ROOT,
            status=DecisionStatus.SATISFIED,
            subject=CourseIdentity.parse("R23:CAIE:CSE341"),
        )
    )
    provenance = Provenance(
        source_id="SRC-2023",
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    metadata = ResultMetadata(
        dataset_version=DatasetVersion("foundation-1.0.0-dev", source="academic-data"),
        execution_mode=ExecutionMode.AUTHORITATIVE,
        authoritative=True,
        engine_version="planning-contracts-0.1.0",
        ruleset_version="rules-2023-1",
        warnings=(ReasonCode.UNSUPPORTED_CASE,),
        reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
        provenance=(provenance,),
        decision_trace=trace,
        requires_human_review=False,
    )

    serialized = metadata.to_dict()

    assert serialized["dataset_version"]["version"] == "foundation-1.0.0-dev"
    assert serialized["execution_mode"] == "AUTHORITATIVE"
    assert serialized["authoritative"] is True
    assert serialized["ruleset_version"] == "rules-2023-1"
    assert serialized["reason_codes"] == ["MISSING_REQUIRED_DATA"]
    assert serialized["provenance"][0]["approval_status"] == "APPROVED"
    assert serialized["decision_trace"]["root"]["status"] == "SATISFIED"


def test_result_metadata_from_development_policy_is_non_authoritative() -> None:
    policy_decision = ExecutionPolicy.development().assess(
        ApprovalStatus.SOURCE_VERIFIED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        critical=True,
    )

    metadata = ResultMetadata.from_policy(
        dataset_version=DatasetVersion("foundation-1.0.0-dev"),
        decision=policy_decision,
    )

    assert metadata.authoritative is False
    assert metadata.execution_mode is ExecutionMode.DEVELOPMENT
    assert metadata.approval_status is ApprovalStatus.SOURCE_VERIFIED
    assert metadata.verification_status is VerificationStatus.SOURCE_VERIFIED
    assert metadata.requires_human_review is False
    assert ReasonCode.UNAPPROVED_RULE in metadata.reason_codes


def test_result_metadata_rejects_inconsistent_authoritative_state() -> None:
    with pytest.raises(ValueError):
        ResultMetadata(
            dataset_version=DatasetVersion("foundation-1.0.0-dev"),
            execution_mode=ExecutionMode.DEVELOPMENT,
            authoritative=True,
        )

    with pytest.raises(ValueError):
        ResultMetadata(
            dataset_version=DatasetVersion("foundation-1.0.0-dev"),
            execution_mode=ExecutionMode.AUTHORITATIVE,
            authoritative=True,
            requires_human_review=True,
        )

    with pytest.raises(ValueError):
        ResultMetadata(
            dataset_version=DatasetVersion("foundation-1.0.0-dev"),
            execution_mode=ExecutionMode.AUTHORITATIVE,
            authoritative=True,
            approval_status=ApprovalStatus.SOURCE_VERIFIED,
        )
