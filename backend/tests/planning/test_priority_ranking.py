from __future__ import annotations

from app.planning.ranking.service import PriorityRankingService
from app.planning.domain.candidates import (
    CandidateAvailability,
    CandidateCourse,
    CandidateReasonCode,
)
from app.planning.domain.course import (
    Course,
    CourseIdentity,
    Program,
    Regulation,
)
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
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


R23 = Regulation.R23
CAIE = Program("CAIE")
VERSION = DatasetVersion("ranking-test")


def candidate(code: str, reasons: tuple[CandidateReasonCode, ...]) -> CandidateCourse:
    course = Course(
        CourseIdentity(R23, CAIE, code),
        code,
        3,
        ApprovalStatus.APPROVED,
        VerificationStatus.SOURCE_VERIFIED,
    )
    trace = DecisionTrace(
        DecisionTraceNode(
            node_id=f"candidate:{code}",
            code=TraceCode.CANDIDATE,
            node_type=TraceNodeType.REQUIREMENT_CHECK,
            status=DecisionStatus.SATISFIED,
        )
    )
    metadata = ResultMetadata(
        dataset_version=VERSION,
        execution_mode=ExecutionMode.DEVELOPMENT,
        authoritative=False,
        decision_trace=trace,
    )
    return CandidateCourse(
        course=course,
        eligibility=None,
        availability=CandidateAvailability.AVAILABLE,
        reason_codes=reasons,
        metadata=metadata,
    )


def test_required_candidate_precedes_unlock_only_candidate_deterministically() -> None:
    required = candidate("CSE341", (CandidateReasonCode.REQUIRED_FOR_PROGRAM,))
    unlock = candidate("CSE241", (CandidateReasonCode.UNLOCKS_REQUIRED_COURSE,))

    result = PriorityRankingService(VERSION).rank((unlock, required))

    assert [item.candidate.course.identity.course_code for item in result.items] == [
        "CSE341",
        "CSE241",
    ]
    assert result.items[0].rank == 1
    assert (
        result.items[0].factors.requirement_rank
        < result.items[1].factors.requirement_rank
    )


def test_canonical_identity_breaks_equal_priority_ties() -> None:
    first = candidate("CSE241", (CandidateReasonCode.ELECTIVE_REQUIREMENT,))
    second = candidate("CSE242", (CandidateReasonCode.ELECTIVE_REQUIREMENT,))

    forward = PriorityRankingService(VERSION).rank((first, second))
    reverse = PriorityRankingService(VERSION).rank((second, first))

    assert [item.candidate.identity.course_code for item in forward.items] == [
        "CSE241",
        "CSE242",
    ]
    assert forward.to_dict() == reverse.to_dict()


def test_available_candidate_precedes_equivalent_conditional_candidate() -> None:
    available = candidate("CSE241", (CandidateReasonCode.ELECTIVE_REQUIREMENT,))
    conditional = CandidateCourse(
        course=available.course.__class__(
            CourseIdentity(R23, CAIE, "CSE242"),
            "CSE242",
            3,
            ApprovalStatus.APPROVED,
            VerificationStatus.SOURCE_VERIFIED,
        ),
        eligibility=None,
        availability=CandidateAvailability.CONDITIONAL,
        reason_codes=(CandidateReasonCode.ELECTIVE_REQUIREMENT,),
        metadata=available.metadata,
    )

    result = PriorityRankingService(VERSION).rank((conditional, available))

    assert result.items[0].candidate.identity.course_code == "CSE241"
    assert result.items[0].factors.eligibility_rank == 0
    assert result.items[1].factors.eligibility_rank == 1


def test_unlock_and_concentration_factors_are_structured() -> None:
    unlock = CandidateCourse(
        course=Course(
            CourseIdentity(R23, CAIE, "CSE243"),
            "CSE243",
            3,
            ApprovalStatus.APPROVED,
            VerificationStatus.SOURCE_VERIFIED,
        ),
        eligibility=None,
        availability=CandidateAvailability.AVAILABLE,
        reason_codes=(
            CandidateReasonCode.UNLOCKS_MULTIPLE_COURSES,
            CandidateReasonCode.CONCENTRATION_PROGRESS,
        ),
        unlocks=(
            CourseIdentity(R23, CAIE, "CSE341"),
            CourseIdentity(R23, CAIE, "CSE342"),
        ),
        metadata=candidate("CSE241", ()).metadata,
    )

    result = PriorityRankingService(VERSION).rank((unlock,))

    factors = result.items[0].factors
    assert factors.unlock_count == 2
    assert factors.concentration_contribution == 1
    assert "score" not in result.to_dict()["items"][0]["factors"]
