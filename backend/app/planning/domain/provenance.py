"""Structured provenance attached to planning decisions."""

from __future__ import annotations

from dataclasses import dataclass

from .lifecycle import ApprovalStatus, VerificationStatus


SourcePage = int | str


@dataclass(frozen=True, slots=True)
class Provenance:
    """Optional rule/source evidence for a domain result or trace node."""

    rule_id: str | None = None
    source_id: str | None = None
    source_page: SourcePage | None = None
    approval_status: ApprovalStatus | None = None
    verification_status: VerificationStatus | None = None

    def __post_init__(self) -> None:
        for name in ("rule_id", "source_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string when provided")
        if self.approval_status is not None and not isinstance(
            self.approval_status, ApprovalStatus
        ):
            raise TypeError("approval_status must be an ApprovalStatus or None")
        if self.verification_status is not None and not isinstance(
            self.verification_status, VerificationStatus
        ):
            raise TypeError("verification_status must be a VerificationStatus or None")
        if self.source_page is not None and not isinstance(
            self.source_page, (int, str)
        ):
            raise TypeError("source_page must be an integer, string, or None")
        if isinstance(self.source_page, bool):
            raise ValueError("source_page must be an integer or string, not bool")
        if isinstance(self.source_page, int) and self.source_page < 1:
            raise ValueError("source_page must be positive when numeric")
        if isinstance(self.source_page, str) and not self.source_page.strip():
            raise ValueError("source_page must be non-empty when textual")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation without prose generation."""

        values: dict[str, object] = {}
        for field_name in (
            "rule_id",
            "source_id",
            "source_page",
            "approval_status",
            "verification_status",
        ):
            value = getattr(self, field_name)
            if value is not None:
                values[field_name] = (
                    value.value
                    if isinstance(value, (ApprovalStatus, VerificationStatus))
                    else value
                )
        return values
