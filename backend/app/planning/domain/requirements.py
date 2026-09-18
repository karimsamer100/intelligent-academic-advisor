"""Minimal program-requirement records for repository contracts."""

from __future__ import annotations

from dataclasses import dataclass

from .course import Program, Regulation
from .lifecycle import ApprovalStatus, VerificationStatus
from .provenance import Provenance


@dataclass(frozen=True, slots=True)
class ProgramRequirement:
    """Requirement identity and safety metadata without evaluation behavior."""

    requirement_id: str
    regulation: Regulation
    program: Program
    approval_status: ApprovalStatus
    verification_status: VerificationStatus
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.requirement_id, str) or not self.requirement_id.strip():
            raise ValueError("requirement_id must be a non-empty string")
        if not isinstance(self.regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(self.program, Program):
            raise TypeError("program must be a Program")
        if not isinstance(self.approval_status, ApprovalStatus):
            raise TypeError("approval_status must be an ApprovalStatus")
        if not isinstance(self.verification_status, VerificationStatus):
            raise TypeError("verification_status must be a VerificationStatus")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")
