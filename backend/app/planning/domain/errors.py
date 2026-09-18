"""Typed errors and structured issues for planning-domain boundaries."""

from dataclasses import dataclass
from enum import StrEnum

from .reasons import ReasonCode


class PlanningErrorCode(StrEnum):
    """Failure categories used at Planning Engine integration boundaries."""

    INVALID_REQUEST = "INVALID_REQUEST"
    DATA_NOT_FOUND = "DATA_NOT_FOUND"
    UNSUPPORTED_RULE = "UNSUPPORTED_RULE"
    CONFLICTED_RULE = "CONFLICTED_RULE"
    UNAPPROVED_RULE = "UNAPPROVED_RULE"
    INTERNAL_ENGINE_ERROR = "INTERNAL_ENGINE_ERROR"


@dataclass(frozen=True, slots=True)
class DomainIssue:
    """A structured, expected domain outcome that is not a system exception.

    Academic uncertainty such as a conflicted or unapproved rule should be
    represented as an issue and carried by a result contract. It should not be
    converted into an untyped exception or silently resolved by the engine.
    """

    code: PlanningErrorCode
    reason_codes: tuple[ReasonCode, ...] = ()
    requires_human_review: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.code, PlanningErrorCode):
            raise TypeError("code must be a PlanningErrorCode")

        normalized_reasons = tuple(self.reason_codes)
        if not all(isinstance(reason, ReasonCode) for reason in normalized_reasons):
            raise TypeError("reason_codes must contain only ReasonCode values")
        if not isinstance(self.requires_human_review, bool):
            raise TypeError("requires_human_review must be a bool")
        object.__setattr__(self, "reason_codes", normalized_reasons)

    def to_dict(self) -> dict[str, object]:
        """Return a stable machine-readable representation."""

        return {
            "code": self.code.value,
            "reason_codes": [reason.value for reason in self.reason_codes],
            "requires_human_review": self.requires_human_review,
        }


class PlanningDomainError(Exception):
    """Typed exception for invalid boundaries and unrecoverable engine errors.

    Normal academic uncertainty belongs in :class:`DomainIssue` and result
    metadata. This exception is reserved for programmer/system-level failure
    paths such as invalid requests or an internal engine failure.
    """

    def __init__(
        self,
        code: PlanningErrorCode,
        detail: str | None = None,
    ) -> None:
        if not isinstance(code, PlanningErrorCode):
            raise TypeError("code must be a PlanningErrorCode")
        self.code = code
        self.detail = detail
        super().__init__(detail or code.value)
