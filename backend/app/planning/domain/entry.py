"""Typed boundary for admission, placement, and foundation requirements."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .provenance import Provenance


class RequirementApplicability(StrEnum):
    APPLIES = "APPLIES"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class EntryRequirementReference:
    """Opaque source reference kept separate from ordinary course identity."""

    code: str
    applicability: RequirementApplicability = RequirementApplicability.UNKNOWN
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("code must be a non-empty string")
        if not isinstance(self.applicability, RequirementApplicability):
            raise TypeError("applicability must be a RequirementApplicability")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "applicability": self.applicability.value,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }
