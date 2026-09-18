import pytest

from backend.app.planning.domain.errors import (
    DomainIssue,
    PlanningDomainError,
    PlanningErrorCode,
)
from backend.app.planning.domain.reasons import ReasonCode


def test_academic_uncertainty_is_a_structured_domain_issue() -> None:
    issue = DomainIssue(
        code=PlanningErrorCode.CONFLICTED_RULE,
        reason_codes=(ReasonCode.CONFLICTED_RULE,),
        requires_human_review=True,
    )

    assert issue.code is PlanningErrorCode.CONFLICTED_RULE
    assert issue.reason_codes == (ReasonCode.CONFLICTED_RULE,)
    assert issue.requires_human_review is True


def test_typed_domain_exception_preserves_boundary_error_code() -> None:
    with pytest.raises(PlanningDomainError) as captured:
        raise PlanningDomainError(PlanningErrorCode.INVALID_REQUEST)

    assert captured.value.code is PlanningErrorCode.INVALID_REQUEST


def test_domain_issue_requires_boolean_review_state() -> None:
    with pytest.raises(TypeError):
        DomainIssue(
            code=PlanningErrorCode.UNSUPPORTED_RULE,
            requires_human_review=1,  # type: ignore[arg-type]
        )
