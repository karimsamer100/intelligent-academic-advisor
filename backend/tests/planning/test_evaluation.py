from app.planning.domain.evaluation import (
    EvaluationOutcome,
    RuleEvaluationResult,
)
from app.planning.domain.results import ResultMetadata
from app.planning.domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceNodeType,
)
from app.planning.domain.version import DatasetVersion
from app.planning.policy import ExecutionMode


def test_rule_evaluation_result_composes_metadata_and_trace() -> None:
    trace = DecisionTrace(
        DecisionTraceNode(
            node_id="rule",
            code=TraceCode.RULE,
            node_type=TraceNodeType.RULE_CHECK,
            status=DecisionStatus.SATISFIED,
        )
    )
    metadata = ResultMetadata(
        dataset_version=DatasetVersion("academic-dev-1"),
        execution_mode=ExecutionMode.DEVELOPMENT,
        authoritative=False,
        decision_trace=trace,
    )

    result = RuleEvaluationResult(
        rule_id="R23-PR-CSE341",
        outcome=EvaluationOutcome.SATISFIED,
        metadata=metadata,
    )

    assert result.outcome is EvaluationOutcome.SATISFIED
    assert result.authoritative is False
    assert result.decision_trace is trace
    assert result.to_dict()["outcome"] == "SATISFIED"
