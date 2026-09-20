"""Deterministic lexicographic ranking of academically relevant candidates."""

from __future__ import annotations

from collections.abc import Iterable

from ..domain.candidates import (
    CandidateAvailability,
    CandidateCourse,
    CandidateGenerationResult,
    CandidateReasonCode,
)
from ..domain.ranking import PriorityFactors, PriorityRankingResult, RankedCandidate
from ..domain.results import ResultMetadata
from ..domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceMetadata,
    TraceNodeType,
)
from ..domain.version import DatasetVersion
from ..policy import ExecutionMode, ExecutionPolicy


class PriorityRankingService:
    """Rank supplied candidates without personalization or magic weights."""

    def __init__(
        self,
        dataset_version: DatasetVersion,
        policy: ExecutionPolicy | None = None,
    ) -> None:
        if not isinstance(dataset_version, DatasetVersion):
            raise TypeError("dataset_version must be a DatasetVersion")
        if policy is not None and not isinstance(policy, ExecutionPolicy):
            raise TypeError("policy must be an ExecutionPolicy or None")
        self._dataset_version = dataset_version
        self._policy = policy or ExecutionPolicy.development()

    def rank(
        self,
        candidates: CandidateGenerationResult | Iterable[CandidateCourse],
    ) -> PriorityRankingResult:
        if isinstance(candidates, CandidateGenerationResult):
            values = candidates.candidates
            coverage_complete = candidates.status.value == "COMPLETE"
        else:
            values = tuple(candidates)
            coverage_complete = True
        values = tuple(values)
        if not all(isinstance(item, CandidateCourse) for item in values):
            raise TypeError("candidates must contain CandidateCourse values")
        if len({item.identity for item in values}) != len(values):
            raise ValueError("candidates must have unique canonical identities")
        ordered = sorted(
            values,
            key=lambda item: (
                _factors_for(item).sort_key(),
                item.identity.course_id,
            ),
        )
        ranked: list[RankedCandidate] = []
        for rank, candidate in enumerate(ordered, start=1):
            factors = _factors_for(candidate)
            ranked.append(
                RankedCandidate(
                    candidate=candidate,
                    rank=rank,
                    factors=factors,
                    trace=_priority_trace(candidate, factors, rank),
                )
            )
        trace = _ranking_trace(ranked)
        review = not coverage_complete or any(
            item.candidate.availability is CandidateAvailability.REVIEW_REQUIRED
            for item in ranked
        )
        authoritative = (
            self._policy.mode is ExecutionMode.AUTHORITATIVE
            and coverage_complete
            and not review
            and all(
                item.candidate.metadata is not None
                and item.candidate.metadata.authoritative
                for item in ranked
            )
        )
        metadata = ResultMetadata(
            dataset_version=self._dataset_version,
            execution_mode=self._policy.mode,
            authoritative=authoritative,
            provenance=tuple(
                provenance
                for item in ranked
                for provenance in (
                    (
                        *(
                            item.candidate.metadata.provenance
                            if item.candidate.metadata is not None
                            else ()
                        ),
                        *item.candidate.uel_provenance,
                    )
                )
            ),
            decision_trace=trace,
            requires_human_review=review,
        )
        return PriorityRankingResult(tuple(ranked), metadata, trace)


def _factors_for(candidate: CandidateCourse) -> PriorityFactors:
    eligibility_rank = {
        CandidateAvailability.AVAILABLE: 0,
        CandidateAvailability.CONDITIONAL: 1,
        CandidateAvailability.REVIEW_REQUIRED: 2,
    }[candidate.availability]
    required = bool(
        {
            CandidateReasonCode.REQUIRED_FOR_PROGRAM,
            CandidateReasonCode.REQUIRED_ZERO_CREDIT,
        }
        & set(candidate.reason_codes)
    )
    concentration = CandidateReasonCode.CONCENTRATION_PROGRESS in candidate.reason_codes
    elective = CandidateReasonCode.ELECTIVE_REQUIREMENT in candidate.reason_codes
    if required:
        requirement_rank = 0
    elif concentration:
        requirement_rank = 1
    elif elective:
        requirement_rank = 2
    elif candidate.unlocks:
        requirement_rank = 3
    else:
        requirement_rank = 4
    return PriorityFactors(
        eligibility_rank=eligibility_rank,
        requirement_rank=requirement_rank,
        blocker_rank=0 if required else 1,
        unlock_count=len(candidate.unlocks),
        concentration_contribution=1 if concentration else 0,
        elective_contribution=1 if elective else 0,
        external_progression_risk=(
            1
            if CandidateReasonCode.UEL_PROGRESSION_RISK in candidate.reason_codes
            else 0
        ),
    )


def _priority_trace(candidate, factors, rank):
    return DecisionTrace(
        DecisionTraceNode(
            node_id=f"priority:{candidate.identity.course_id}",
            code=TraceCode.PRIORITY,
            node_type=TraceNodeType.VALUE_CHECK,
            status=DecisionStatus.SATISFIED,
            subject=candidate.identity,
            actual_value=rank,
            provenance=candidate.uel_provenance,
            metadata=tuple(
                TraceMetadata(key, value)
                for key, value in factors.to_dict().items()
                if isinstance(value, (str, int, float, bool)) or value is None
            ),
        )
    )


def _ranking_trace(ranked):
    return DecisionTrace(
        DecisionTraceNode(
            node_id="priority-ranking",
            code=TraceCode.PRIORITY_RANKING,
            node_type=TraceNodeType.ROOT,
            status=DecisionStatus.SATISFIED,
            children=tuple(item.trace.root for item in ranked),
        )
    )


__all__ = ["PriorityRankingService"]
