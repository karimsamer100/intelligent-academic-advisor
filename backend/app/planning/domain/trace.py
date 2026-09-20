"""Immutable, machine-readable decision traces for future rule evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from .course import CourseIdentity
from .provenance import Provenance
from .reasons import ReasonCode


TraceValue = str | int | float | bool | None | tuple[str, ...]


class TraceNodeType(StrEnum):
    ROOT = "ROOT"
    LOGICAL = "LOGICAL"
    RULE_CHECK = "RULE_CHECK"
    COURSE_CHECK = "COURSE_CHECK"
    VALUE_CHECK = "VALUE_CHECK"
    REQUIREMENT_CHECK = "REQUIREMENT_CHECK"


class DecisionStatus(StrEnum):
    SATISFIED = "SATISFIED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"
    BLOCKED = "BLOCKED"
    CONFLICTED = "CONFLICTED"
    NOT_EVALUATED = "NOT_EVALUATED"
    UNSUPPORTED = "UNSUPPORTED"
    CONDITIONAL = "CONDITIONAL"
    ADVISOR_REVIEW = "ADVISOR_REVIEW"


class TraceCode(StrEnum):
    DEGREE_AUDIT = "DEGREE_AUDIT"
    REQUIREMENT_SET_COVERAGE = "REQUIREMENT_SET_COVERAGE"
    ELIGIBILITY = "ELIGIBILITY"
    SCOPE_CHECK = "SCOPE_CHECK"
    COURSE_LIFECYCLE = "COURSE_LIFECYCLE"
    NOT_ALREADY_COMPLETED = "NOT_ALREADY_COMPLETED"
    NOT_CURRENTLY_REGISTERED = "NOT_CURRENTLY_REGISTERED"
    RULE_SET_AVAILABILITY = "RULE_SET_AVAILABILITY"
    PROPOSED_TERM_CONTEXT = "PROPOSED_TERM_CONTEXT"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    RULE = "RULE"
    REQUIREMENT = "REQUIREMENT"
    COURSE_PASSED = "COURSE_PASSED"
    COURSE_COMPLETED = "COURSE_COMPLETED"
    COURSE_CURRENTLY_REGISTERED = "COURSE_CURRENTLY_REGISTERED"
    COURSE_CONCURRENT = "COURSE_CONCURRENT"
    MIN_GRADE = "MIN_GRADE"
    MIN_EARNED_CREDITS = "MIN_EARNED_CREDITS"
    MAX_EARNED_CREDITS = "MAX_EARNED_CREDITS"
    MIN_GPA = "MIN_GPA"
    MAX_GPA = "MAX_GPA"
    COREQUISITE = "COREQUISITE"
    REQUIREMENT_COMPLETED = "REQUIREMENT_COMPLETED"
    TOTAL_PROGRAM_CREDITS = "TOTAL_PROGRAM_CREDITS"
    POOL_COUNT = "POOL_COUNT"
    CONCENTRATION = "CONCENTRATION"
    ELECTIVE_SLOT = "ELECTIVE_SLOT"
    FIELD_TRAINING = "FIELD_TRAINING"
    SEMESTER_VALIDATION = "SEMESTER_VALIDATION"
    LOAD_POLICY = "LOAD_POLICY"
    COURSE_VALIDATION = "COURSE_VALIDATION"
    CANDIDATE_GENERATION = "CANDIDATE_GENERATION"
    CANDIDATE = "CANDIDATE"
    PRIORITY_RANKING = "PRIORITY_RANKING"
    PRIORITY = "PRIORITY"
    SINGLE_SEMESTER_PLANNING = "SINGLE_SEMESTER_PLANNING"
    PLANNING_PREFERENCES = "PLANNING_PREFERENCES"
    PLAN_SELECTION = "PLAN_SELECTION"
    PLAN_ALTERNATIVE = "PLAN_ALTERNATIVE"
    HYPOTHETICAL_TRANSITION = "HYPOTHETICAL_TRANSITION"
    MULTI_SEMESTER_PLANNING = "MULTI_SEMESTER_PLANNING"
    PROJECTION = "PROJECTION"
    OFFERING_COVERAGE = "OFFERING_COVERAGE"
    TIMETABLE_COVERAGE = "TIMETABLE_COVERAGE"
    WHAT_IF = "WHAT_IF"
    UEL_PROGRESS = "UEL_PROGRESS"
    UEL_MAPPING = "UEL_MAPPING"
    UEL_RISK = "UEL_RISK"


@dataclass(frozen=True, slots=True)
class TraceMetadata:
    """A bounded metadata entry; arbitrary nested dictionaries are disallowed."""

    key: str
    value: TraceValue

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("trace metadata key must be a non-empty string")
        if not _is_trace_value(self.value):
            raise TypeError("trace metadata value must be a supported scalar value")


@dataclass(frozen=True, slots=True)
class DecisionTraceNode:
    """One node in an immutable recursive decision tree."""

    node_id: str
    code: TraceCode
    node_type: TraceNodeType
    status: DecisionStatus
    subject: CourseIdentity | str | None = None
    expected_value: TraceValue = None
    actual_value: TraceValue = None
    reason_codes: tuple[ReasonCode, ...] = ()
    children: tuple["DecisionTraceNode", ...] = ()
    provenance: tuple[Provenance, ...] = ()
    metadata: tuple[TraceMetadata, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id.strip():
            raise ValueError("trace node_id must be a non-empty string")
        if not isinstance(self.code, TraceCode):
            raise TypeError("trace code must be a TraceCode")
        if not isinstance(self.node_type, TraceNodeType):
            raise TypeError("trace node_type must be a TraceNodeType")
        if not isinstance(self.status, DecisionStatus):
            raise TypeError("trace status must be a DecisionStatus")
        if self.subject is not None and not isinstance(
            self.subject, (CourseIdentity, str)
        ):
            raise TypeError("trace subject must be a CourseIdentity, string, or None")
        if isinstance(self.subject, str) and not self.subject.strip():
            raise ValueError("trace subject must be non-empty when provided")
        if not _is_trace_value(self.expected_value) or not _is_trace_value(
            self.actual_value
        ):
            raise TypeError(
                "trace expected and actual values must be supported scalars"
            )
        reason_codes = tuple(self.reason_codes)
        children = tuple(self.children)
        provenance = tuple(self.provenance)
        metadata = tuple(self.metadata)
        if not all(isinstance(code, ReasonCode) for code in reason_codes):
            raise TypeError("trace reason_codes must contain only ReasonCode values")
        if not all(isinstance(child, DecisionTraceNode) for child in children):
            raise TypeError("trace children must contain only DecisionTraceNode values")
        if not all(isinstance(item, Provenance) for item in provenance):
            raise TypeError("trace provenance must contain only Provenance values")
        if not all(isinstance(entry, TraceMetadata) for entry in metadata):
            raise TypeError("trace metadata must contain only TraceMetadata values")
        object.__setattr__(self, "reason_codes", reason_codes)
        object.__setattr__(self, "children", children)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "metadata", metadata)
        metadata_keys = [entry.key for entry in metadata]
        if len(metadata_keys) != len(set(metadata_keys)):
            raise ValueError("trace metadata keys must be unique")

    @property
    def expected(self) -> TraceValue:
        return self.expected_value

    @property
    def actual(self) -> TraceValue:
        return self.actual_value

    @property
    def outcome(self) -> DecisionStatus:
        return self.status

    def to_dict(self) -> dict[str, object]:
        """Serialize the node without generating natural-language explanations."""

        result: dict[str, object] = {
            "node_id": self.node_id,
            "code": self.code.value,
            "node_type": self.node_type.value,
            "status": self.status.value,
            "reason_codes": [code.value for code in self.reason_codes],
            "children": [child.to_dict() for child in self.children],
            "provenance": [item.to_dict() for item in self.provenance],
            "metadata": {
                item.key: _serialize_value(item.value) for item in self.metadata
            },
        }
        if self.subject is not None:
            result["subject"] = str(self.subject)
        if self.expected_value is not None:
            result["expected_value"] = _serialize_value(self.expected_value)
        if self.actual_value is not None:
            result["actual_value"] = _serialize_value(self.actual_value)
        return result


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    """Rooted decision trace that can be attached to a future result."""

    root: DecisionTraceNode

    def __post_init__(self) -> None:
        if not isinstance(self.root, DecisionTraceNode):
            raise TypeError("trace root must be a DecisionTraceNode")

    def to_dict(self) -> dict[str, object]:
        return {"root": self.root.to_dict()}

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )


def _is_trace_value(value: object) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    return isinstance(value, tuple) and all(isinstance(item, str) for item in value)


def _serialize_value(value: TraceValue) -> object:
    return list(value) if isinstance(value, tuple) else value
