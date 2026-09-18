"""Academic-data verification and approval states.

Verification and academic approval are intentionally separate.  A record can
be source-verified while still being blocked or otherwise not approved for
authoritative planning decisions.
"""

from enum import StrEnum


class VerificationStatus(StrEnum):
    """Evidence-verification state used by the current data foundation."""

    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    SOURCE_VERIFIED = "SOURCE_VERIFIED"

    @classmethod
    def from_raw(cls, value: str) -> "VerificationStatus":
        """Convert a persisted value without silently inventing a mapping."""

        try:
            return cls(value)
        except ValueError as error:
            raise ValueError(f"Unknown verification status: {value!r}") from error

    @property
    def is_source_verified(self) -> bool:
        return self is VerificationStatus.SOURCE_VERIFIED


class ApprovalStatus(StrEnum):
    """Academic safety/lifecycle state from the data foundation contracts."""

    EXTRACTED = "EXTRACTED"
    SOURCE_VERIFIED = "SOURCE_VERIFIED"
    ACADEMICALLY_REVIEWED = "ACADEMICALLY_REVIEWED"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    SUPERSEDED = "SUPERSEDED"
    CONFLICTED = "CONFLICTED"
    PENDING_ACADEMIC_REVIEW = "PENDING_ACADEMIC_REVIEW"

    @classmethod
    def from_raw(cls, value: str) -> "ApprovalStatus":
        """Convert an Academic Data Foundation approval value strictly."""

        try:
            return cls(value)
        except ValueError as error:
            raise ValueError(f"Unknown approval status: {value!r}") from error

    @property
    def is_academically_approved(self) -> bool:
        return self is ApprovalStatus.APPROVED

    @property
    def requires_human_review(self) -> bool:
        return self in {
            ApprovalStatus.BLOCKED,
            ApprovalStatus.CONFLICTED,
            ApprovalStatus.PENDING_ACADEMIC_REVIEW,
        }
