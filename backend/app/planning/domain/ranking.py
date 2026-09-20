"""Deterministic, factorized candidate-priority contracts."""

from __future__ import annotations

from dataclasses import dataclass

from .candidates import CandidateCourse
from .results import ResultMetadata
from .trace import DecisionTrace


@dataclass(frozen=True, slots=True)
class PriorityFactors:
    """Explicit lexicographic factors; no opaque aggregate score."""

    eligibility_rank: int
    requirement_rank: int
    blocker_rank: int
    unlock_count: int
    concentration_contribution: int
    elective_contribution: int
    external_progression_risk: int = 0

    def __post_init__(self) -> None:
        for name in (
            "eligibility_rank",
            "requirement_rank",
            "blocker_rank",
            "unlock_count",
            "concentration_contribution",
            "elective_contribution",
            "external_progression_risk",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    def sort_key(self) -> tuple[int, int, int, int, int, int, int]:
        """Return the deterministic ordering key used by the ranking service."""

        return (
            self.eligibility_rank,
            self.requirement_rank,
            self.blocker_rank,
            -self.external_progression_risk,
            -self.unlock_count,
            -self.concentration_contribution,
            -self.elective_contribution,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "eligibility_rank": self.eligibility_rank,
            "requirement_rank": self.requirement_rank,
            "blocker_rank": self.blocker_rank,
            "unlock_count": self.unlock_count,
            "concentration_contribution": self.concentration_contribution,
            "elective_contribution": self.elective_contribution,
            "external_progression_risk": self.external_progression_risk,
        }


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: CandidateCourse
    rank: int
    factors: PriorityFactors
    trace: DecisionTrace

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, CandidateCourse):
            raise TypeError("candidate must be a CandidateCourse")
        if (
            isinstance(self.rank, bool)
            or not isinstance(self.rank, int)
            or self.rank < 1
        ):
            raise ValueError("rank must be a positive integer")
        if not isinstance(self.factors, PriorityFactors):
            raise TypeError("factors must be PriorityFactors")
        if not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace")

    def to_dict(self) -> dict[str, object]:
        return {
            "course": self.candidate.course.identity.course_id,
            "rank": self.rank,
            "factors": self.factors.to_dict(),
            "candidate": self.candidate.to_dict(),
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PriorityRankingResult:
    items: tuple[RankedCandidate, ...]
    metadata: ResultMetadata
    trace: DecisionTrace

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if not all(isinstance(item, RankedCandidate) for item in items):
            raise TypeError("items must contain RankedCandidate values")
        ranks = tuple(item.rank for item in items)
        if ranks != tuple(range(1, len(items) + 1)):
            raise ValueError("ranking ranks must be contiguous and one-based")
        if len({item.candidate.identity for item in items}) != len(items):
            raise ValueError("ranking cannot contain duplicate candidate identities")
        if not isinstance(self.metadata, ResultMetadata):
            raise TypeError("metadata must be a ResultMetadata")
        if not isinstance(self.trace, DecisionTrace):
            raise TypeError("trace must be a DecisionTrace")
        object.__setattr__(self, "items", items)

    def to_dict(self) -> dict[str, object]:
        return {
            "items": [item.to_dict() for item in self.items],
            "metadata": self.metadata.to_dict(),
            "trace": self.trace.to_dict(),
        }


__all__ = ["PriorityFactors", "PriorityRankingResult", "RankedCandidate"]
