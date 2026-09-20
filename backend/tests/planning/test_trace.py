import json

import pytest

from app.planning.domain.course import CourseIdentity
from app.planning.domain.provenance import Provenance
from app.planning.domain.reasons import ReasonCode
from app.planning.domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceMetadata,
    TraceNodeType,
)


def test_nested_decision_trace_represents_machine_readable_rule_tree() -> None:
    passed_prerequisite = DecisionTraceNode(
        node_id="prerequisite-course",
        code=TraceCode.COURSE_PASSED,
        node_type=TraceNodeType.COURSE_CHECK,
        status=DecisionStatus.SATISFIED,
        subject=CourseIdentity.parse("R23:CAIE:CSE241"),
    )
    earned_credits = DecisionTraceNode(
        node_id="earned-credits",
        code=TraceCode.MIN_EARNED_CREDITS,
        node_type=TraceNodeType.VALUE_CHECK,
        status=DecisionStatus.FAILED,
        expected_value=60,
        actual_value=45,
        reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
        metadata=(TraceMetadata("basis", "academic_snapshot"),),
    )
    root = DecisionTraceNode(
        node_id="eligibility-cse341",
        code=TraceCode.ELIGIBILITY,
        node_type=TraceNodeType.ROOT,
        status=DecisionStatus.FAILED,
        subject=CourseIdentity.parse("R23:CAIE:CSE341"),
        children=(passed_prerequisite, earned_credits),
        provenance=(Provenance(rule_id="R23-PR-CSE341", source_id="SRC-2023"),),
    )

    trace = DecisionTrace(root)
    serialized = trace.to_dict()

    assert serialized["root"]["code"] == "ELIGIBILITY"
    assert serialized["root"]["subject"] == "R23:CAIE:CSE341"
    assert serialized["root"]["children"][0]["status"] == "SATISFIED"
    assert serialized["root"]["children"][1]["actual_value"] == 45
    assert serialized["root"]["children"][1]["metadata"] == {
        "basis": "academic_snapshot"
    }
    assert serialized["root"]["provenance"][0]["rule_id"] == "R23-PR-CSE341"


def test_decision_trace_serialization_and_equality_are_deterministic() -> None:
    node = DecisionTraceNode(
        node_id="simple-check",
        code=TraceCode.COURSE_COMPLETED,
        node_type=TraceNodeType.RULE_CHECK,
        status=DecisionStatus.NOT_EVALUATED,
    )
    first = DecisionTrace(node)
    second = DecisionTrace(node)

    assert first == second
    assert json.loads(first.to_json()) == first.to_dict()
    assert first.to_json() == second.to_json()


def test_decision_trace_rejects_untyped_tree_members() -> None:
    with pytest.raises(TypeError):
        DecisionTraceNode(
            node_id="invalid-reason",
            code=TraceCode.RULE,
            node_type=TraceNodeType.RULE_CHECK,
            status=DecisionStatus.BLOCKED,
            reason_codes=("BLOCKED_RULE",),  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError):
        DecisionTraceNode(
            node_id="invalid-child",
            code=TraceCode.AND,
            node_type=TraceNodeType.LOGICAL,
            status=DecisionStatus.NOT_EVALUATED,
            children=(object(),),  # type: ignore[arg-type]
        )
