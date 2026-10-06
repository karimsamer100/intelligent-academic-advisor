"""Compact deterministic representations for LLM-facing academic tools.

Planning result objects retain their complete traces and metadata.  These
helpers deliberately select only stable academic facts needed by a future LLM
explanation, so tool messages do not expose the full diagnostic payload.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.planning.domain.audit import (
    CourseRequirementEvidence,
    DegreeAuditResult,
    RequirementEvaluation,
)
from app.planning.domain.conditions import (
    AllConditions,
    AnyConditions,
    CourseMustBePassedCondition,
    FutureCondition,
)
from app.planning.domain.course import Course, CourseIdentity
from app.planning.domain.eligibility import EligibilityResult
from app.planning.domain.provenance import Provenance
from app.planning.domain.trace import DecisionStatus, DecisionTraceNode, TraceCode


# A deterministic character budget is used by tests as a tokenizer-free
# approximation of an approximately 1.5K-token LLM tool message.
DEGREE_AUDIT_PROJECTION_MAX_CHARS = 6000
_MAX_LIST_ITEMS = 20
_COURSE_TRACE_CODES = {
    TraceCode.COURSE_PASSED,
    TraceCode.COURSE_COMPLETED,
    TraceCode.COURSE_CURRENTLY_REGISTERED,
    TraceCode.COURSE_CONCURRENT,
    TraceCode.COREQUISITE,
}
_NON_SATISFIED_STATUSES = {
    DecisionStatus.FAILED,
    DecisionStatus.INDETERMINATE,
    DecisionStatus.BLOCKED,
    DecisionStatus.CONFLICTED,
    DecisionStatus.UNSUPPORTED,
    DecisionStatus.NOT_EVALUATED,
    DecisionStatus.ADVISOR_REVIEW,
    DecisionStatus.CONDITIONAL,
}


def project_eligibility(
    result: EligibilityResult,
    *,
    course: Course | None = None,
) -> dict[str, Any]:
    """Return the compact LLM representation of one eligibility result."""

    if not isinstance(result, EligibilityResult):
        raise TypeError("result must be an EligibilityResult")

    course_payload: dict[str, str] = {"code": result.target_course.course_code}
    if course is not None and course.identity == result.target_course:
        course_payload["name"] = course.course_name

    return {
        "course": course_payload,
        "decision": result.decision.value,
        "status": result.status.value,
        "eligible": result.eligible,
        "authoritative": result.authoritative,
        "requires_human_review": result.requires_human_review,
        "rule_set_status": result.rule_set_status.value,
        "reasons": _enum_values(result.reason_codes),
        "warnings": _enum_values(result.warnings),
        "missing_requirements": _eligibility_missing_requirements(result),
        "conditions": _eligibility_conditions(result),
        "citations": _eligibility_citations(result),
    }


def project_degree_audit(result: DegreeAuditResult) -> dict[str, Any]:
    """Return a compact progress and review summary for an audit result."""

    if not isinstance(result, DegreeAuditResult):
        raise TypeError("result must be a DegreeAuditResult")

    progress = result.progress
    return {
        "status": result.status.value,
        "requirement_set_status": result.requirement_set_status.value,
        "authoritative": result.authoritative,
        "requires_human_review": result.requires_human_review,
        "reasons": _enum_values(result.reason_codes),
        "credits": {
            "completed": progress.earned_credit_hours,
            "required": progress.required_program_credits,
            "remaining": progress.remaining_known_credits,
        },
        "requirements": _requirement_summary(result),
        "mandatory_missing_courses": _missing_audit_courses(result),
        "elective_progress": _elective_progress(result),
        "warnings": _audit_warnings(result),
        "citations": _audit_citations(result),
    }


def _eligibility_missing_requirements(
    result: EligibilityResult,
) -> list[dict[str, str]]:
    requirements: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for rule_result in result.rule_results:
        for node in _walk_trace(rule_result.decision_trace.root):
            if (
                node.code in _COURSE_TRACE_CODES
                and node.status in _NON_SATISFIED_STATUSES
                and isinstance(node.subject, CourseIdentity)
            ):
                _append_requirement(
                    requirements,
                    seen,
                    {
                        "type": node.code.value,
                        "course_code": node.subject.course_code,
                    },
                )

    return requirements[:_MAX_LIST_ITEMS]


def _eligibility_conditions(result: EligibilityResult) -> list[dict[str, str]]:
    conditions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for condition in result.conditions:
        for item in _condition_course_requirements(condition):
            _append_requirement(conditions, seen, item)
    return conditions[:_MAX_LIST_ITEMS]


def _condition_course_requirements(
    condition: FutureCondition,
) -> Iterable[dict[str, str]]:
    if isinstance(condition, CourseMustBePassedCondition):
        yield {
            "type": condition.condition_type,
            "course_code": condition.course.course_code,
        }
    elif isinstance(condition, (AllConditions, AnyConditions)):
        for child in condition.children:
            yield from _condition_course_requirements(child)


def _append_requirement(
    values: list[dict[str, str]],
    seen: set[tuple[str, str]],
    value: dict[str, str],
) -> None:
    key = (value["type"], value["course_code"])
    if key not in seen:
        seen.add(key)
        values.append(value)


def _requirement_summary(result: DegreeAuditResult) -> dict[str, Any]:
    remaining = result.unsatisfied_requirements + result.indeterminate_requirements
    details = [
        _compact_requirement(requirement)
        for requirement in remaining[:_MAX_LIST_ITEMS]
    ]
    progress = result.progress
    return {
        "satisfied_count": len(result.satisfied_requirements),
        "total_count": len(result.requirement_results),
        "remaining_ids": _capped_unique(
            progress.outstanding_requirement_ids + progress.unknown_requirement_ids
        ),
        "review_ids": _capped_unique(progress.review_requirement_ids),
        "details": details,
    }


def _compact_requirement(requirement: RequirementEvaluation) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": requirement.requirement_id,
        "type": requirement.definition_type,
        "outcome": requirement.outcome.value,
    }
    if isinstance(requirement.evidence, CourseRequirementEvidence):
        value["course_code"] = requirement.evidence.course.course_code
    return value


def _missing_audit_courses(result: DegreeAuditResult) -> list[str]:
    courses = [
        requirement.evidence.course.course_code
        for requirement in result.unsatisfied_requirements
        + result.indeterminate_requirements
        if isinstance(requirement.evidence, CourseRequirementEvidence)
    ]
    return list(dict.fromkeys(courses))[:_MAX_LIST_ITEMS]


def _elective_progress(result: DegreeAuditResult) -> list[dict[str, Any]]:
    return [
        {
            "pool_id": item.pool_id.identifier,
            "completed": item.known_passed_count,
            "required": item.required_count,
            "unknown": item.unknown_count,
            "remaining": item.remaining_count,
            "outcome": item.outcome.value,
        }
        for item in result.progress.technical_electives[:_MAX_LIST_ITEMS]
    ]


def _audit_warnings(result: DegreeAuditResult) -> list[str]:
    values = list(_enum_values(result.metadata.warnings))
    for requirement in result.requirement_results:
        values.extend(_enum_values(requirement.warnings))
    return list(dict.fromkeys(values))[:_MAX_LIST_ITEMS]


def _eligibility_citations(result: EligibilityResult) -> list[dict[str, Any]]:
    provenances: list[Provenance] = list(result.metadata.provenance)
    for rule_result in result.rule_results:
        provenances.extend(rule_result.provenance)
        provenances.extend(_trace_provenance(rule_result.decision_trace.root))
    return _compact_citations(provenances)


def _audit_citations(result: DegreeAuditResult) -> list[dict[str, Any]]:
    provenances: list[Provenance] = list(result.metadata.provenance)
    for requirement in result.requirement_results:
        provenances.extend(requirement.provenance)
        provenances.extend(_trace_provenance(requirement.decision_trace.root))
    return _compact_citations(provenances)


def _compact_citations(provenances: Iterable[Provenance]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for provenance in provenances:
        citation: dict[str, Any] = {}
        if provenance.source_id is not None:
            citation["source_id"] = provenance.source_id
        if provenance.source_page is not None:
            citation["page"] = provenance.source_page
        if provenance.rule_id is not None:
            citation["rule_id"] = provenance.rule_id
        if not citation:
            continue
        key = tuple(citation.get(name) for name in ("source_id", "page", "rule_id"))
        if key not in seen:
            seen.add(key)
            citations.append(citation)
        if len(citations) >= _MAX_LIST_ITEMS:
            break
    return citations


def _trace_provenance(node: DecisionTraceNode) -> Iterable[Provenance]:
    yield from node.provenance
    for child in node.children:
        yield from _trace_provenance(child)


def _walk_trace(node: DecisionTraceNode) -> Iterable[DecisionTraceNode]:
    yield node
    for child in node.children:
        yield from _walk_trace(child)


def _capped_unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))[:_MAX_LIST_ITEMS]


def _enum_values(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(value.value for value in values))[:_MAX_LIST_ITEMS]


__all__ = [
    "DEGREE_AUDIT_PROJECTION_MAX_CHARS",
    "project_degree_audit",
    "project_eligibility",
]
