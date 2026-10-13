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
from app.planning.domain.eligibility import (
    CourseEligibilityRuleSet,
    EligibilityResult,
    RuleSetStatus,
)
from app.planning.domain.expressions import (
    AndExpression,
    CourseCompletedExpression,
    CourseConcurrentExpression,
    CourseCurrentlyRegisteredExpression,
    EntryRequirementExpression,
    CoursePassedExpression,
    MaxEarnedCreditsExpression,
    MaxGpaExpression,
    MinEarnedCreditsExpression,
    MinGpaExpression,
    NotExpression,
    OrExpression,
    RuleExpression,
    UnsupportedExpression,
)
from app.planning.domain.lifecycle import ApprovalStatus
from app.planning.domain.provenance import Provenance
from app.planning.domain.reasons import ReasonCode
from app.planning.domain.trace import DecisionStatus, DecisionTraceNode, TraceCode
from app.planning.domain.version import DatasetVersion
from app.planning.repositories.adapters.academic_data_types import (
    AcademicDataDiagnostic,
    AcademicDataLookup,
    AcademicDataSourceMode,
)


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


def project_course_information(
    *,
    course_lookup: AcademicDataLookup[Course],
    rule_lookup: AcademicDataLookup[CourseEligibilityRuleSet],
    source_mode: AcademicDataSourceMode,
    dataset_version: DatasetVersion | None,
) -> dict[str, Any]:
    """Return static course facts without student-specific evaluation."""

    course = course_lookup.value
    if not isinstance(course, Course):
        raise TypeError("course_lookup must contain a Course")
    if not isinstance(source_mode, AcademicDataSourceMode):
        raise TypeError("source_mode must be an AcademicDataSourceMode")

    rule_set = rule_lookup.value
    if rule_set is not None and not isinstance(
        rule_set, CourseEligibilityRuleSet
    ):
        raise TypeError("rule_lookup must contain a CourseEligibilityRuleSet or None")

    rules = (
        [_compact_course_rule(rule) for rule in rule_set.rules]
        if rule_set is not None
        else []
    )
    prerequisite_status = _course_rule_coverage_status(rule_set)
    corequisite_status, corequisite_reason_codes, corequisite_diagnostics = (
        _corequisite_coverage(rule_lookup.diagnostics)
    )
    combined_diagnostics = _compact_diagnostics(
        (*course_lookup.diagnostics, *rule_lookup.diagnostics)
    )
    course_provenance = _compact_provenances(course_lookup.provenance)
    rule_provenance = _compact_provenances(rule_lookup.provenance)

    prerequisite_payload: dict[str, Any] = {
        "status": prerequisite_status,
        "rule_set_status": (
            rule_set.status.value if rule_set is not None else RuleSetStatus.UNAVAILABLE.value
        ),
        "reason_codes": (
            _enum_values(rule_set.reason_codes)
            if rule_set is not None
            else [ReasonCode.MISSING_REQUIRED_DATA.value]
        ),
        "rules": rules,
        "expression": rules[0]["expression"] if len(rules) == 1 else None,
    }
    if rule_provenance:
        prerequisite_payload["provenance"] = rule_provenance

    corequisite_payload: dict[str, Any] = {
        "status": corequisite_status,
        "rules": [],
        "reason": (
            "Complete typed corequisite information is not available "
            "through the Academic Data adapter."
        ),
        "reason_codes": corequisite_reason_codes,
    }
    if corequisite_diagnostics:
        corequisite_payload["diagnostics"] = corequisite_diagnostics

    return {
        "course": {
            "identity": course.identity.course_id,
            "code": course.identity.course_code,
            "name": course.course_name,
            "credit_hours": course.credit_hours,
            "regulation": course.identity.regulation.value,
            "program": str(course.identity.program),
            "approval_status": course.approval_status.value,
            "verification_status": course.verification_status.value,
        },
        "prerequisites": prerequisite_payload,
        "corequisites": corequisite_payload,
        "coverage": {
            "course": "AVAILABLE",
            "prerequisites": prerequisite_status,
            "corequisites": corequisite_status,
        },
        "data_source": {
            "source_mode": source_mode.value,
            "dataset_version": (
                dataset_version.to_dict() if dataset_version is not None else None
            ),
        },
        "course_provenance": course_provenance,
        "authoritative": _course_information_is_authoritative(
            course,
            rule_set,
            source_mode=source_mode,
            corequisite_status=corequisite_status,
        ),
        "diagnostics": combined_diagnostics,
    }


def serialize_rule_expression(expression: RuleExpression) -> dict[str, Any]:
    """Serialize one typed expression without flattening its logical tree."""

    if isinstance(expression, (AndExpression, OrExpression)):
        return {
            "type": expression.expression_type.value,
            "children": [
                serialize_rule_expression(child) for child in expression.children
            ],
        }
    if isinstance(expression, NotExpression):
        return {
            "type": expression.expression_type.value,
            "operand": serialize_rule_expression(expression.operand),
        }
    if isinstance(
        expression,
        (
            CoursePassedExpression,
            CourseCompletedExpression,
            CourseCurrentlyRegisteredExpression,
            CourseConcurrentExpression,
        ),
    ):
        return {
            "type": expression.expression_type.value,
            "course_id": expression.course.course_id,
            "course_code": expression.course.course_code,
        }
    if isinstance(expression, MinEarnedCreditsExpression):
        return {"type": expression.expression_type.value, "minimum": expression.minimum}
    if isinstance(expression, MaxEarnedCreditsExpression):
        return {"type": expression.expression_type.value, "maximum": expression.maximum}
    if isinstance(expression, MinGpaExpression):
        return {"type": expression.expression_type.value, "minimum": expression.minimum}
    if isinstance(expression, MaxGpaExpression):
        return {"type": expression.expression_type.value, "maximum": expression.maximum}
    if isinstance(expression, UnsupportedExpression):
        payload: dict[str, Any] = {
            "type": "UNSUPPORTED",
            "source_type": expression.source_type,
            "supported": False,
        }
        for field_name in (
            "course_id",
            "course_code",
            "code",
            "condition_note",
            "reason",
            "external_reference",
        ):
            value = getattr(expression, field_name)
            if value is not None:
                payload[field_name] = value
        if isinstance(expression, EntryRequirementExpression):
            payload["reference"] = expression.reference.to_dict()
        return payload
    return {
        "type": "UNSUPPORTED",
        "source_type": type(expression).__name__,
        "supported": False,
        "reason": "Expression type is not supported by the course-information serializer",
    }


def _compact_course_rule(rule: Any) -> dict[str, Any]:
    expression = (
        serialize_rule_expression(rule.expression)
        if rule.expression is not None
        else None
    )
    provenance = _compact_provenances(
        (rule.provenance,) if rule.provenance is not None else ()
    )
    return {
        "rule_id": rule.rule_id,
        "expression": expression,
        "approval_status": rule.approval_status.value,
        "verification_status": rule.verification_status.value,
        "critical_for_planner": rule.critical_for_planner,
        "provenance": provenance[0] if provenance else None,
    }


def _course_rule_coverage_status(
    rule_set: CourseEligibilityRuleSet | None,
) -> str:
    if rule_set is None:
        return RuleSetStatus.UNAVAILABLE.value
    if ReasonCode.UNSUPPORTED_RULE in rule_set.reason_codes:
        return "UNSUPPORTED"
    if any(
        rule.expression is not None
        and _serialized_expression_contains_unsupported(
            serialize_rule_expression(rule.expression)
        )
        for rule in rule_set.rules
    ):
        return "UNSUPPORTED"
    if not rule_set.rules or any(rule.expression is None for rule in rule_set.rules):
        return RuleSetStatus.INCOMPLETE.value
    return rule_set.status.value


def _corequisite_coverage(
    diagnostics: Iterable[AcademicDataDiagnostic],
) -> tuple[str, list[str], list[dict[str, Any]]]:
    values = tuple(
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.field == "corequisites"
        or diagnostic.source_type == "corequisites"
    )
    reason_codes = list(
        dict.fromkeys(
            reason.value for diagnostic in values for reason in diagnostic.reason_codes
        )
    )
    compact = _compact_diagnostics(values)
    if any(ReasonCode.UNSUPPORTED_RULE in item.reason_codes for item in values):
        return "UNSUPPORTED", reason_codes, compact
    if values:
        return "INCOMPLETE", reason_codes, compact
    return "UNAVAILABLE", [ReasonCode.MISSING_REQUIRED_DATA.value], compact


def _compact_provenances(
    provenances: Iterable[Provenance],
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for provenance in provenances:
        value: dict[str, Any] = {}
        if provenance.rule_id is not None:
            value["rule_id"] = provenance.rule_id
        if provenance.source_id is not None:
            value["source_id"] = provenance.source_id
        if provenance.source_page is not None:
            value["page"] = provenance.source_page
        if provenance.approval_status is not None:
            value["approval_status"] = provenance.approval_status.value
        if provenance.verification_status is not None:
            value["verification_status"] = provenance.verification_status.value
        key = tuple(
            value.get(name)
            for name in (
                "rule_id",
                "source_id",
                "page",
                "approval_status",
                "verification_status",
            )
        )
        if value and key not in seen:
            seen.add(key)
            values.append(value)
    return values[:_MAX_LIST_ITEMS]


def _compact_diagnostics(
    diagnostics: Iterable[AcademicDataDiagnostic],
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for diagnostic in diagnostics:
        value: dict[str, Any] = {"code": diagnostic.code.value}
        if diagnostic.record_id is not None:
            value["record_id"] = diagnostic.record_id
        if diagnostic.field is not None:
            value["field"] = diagnostic.field
        if diagnostic.source_id is not None:
            value["source_id"] = diagnostic.source_id
        if diagnostic.detail is not None:
            value["detail"] = diagnostic.detail
        if diagnostic.reason_codes:
            value["reason_codes"] = _enum_values(diagnostic.reason_codes)
        values.append(value)
    return values[:_MAX_LIST_ITEMS]


def _course_information_is_authoritative(
    course: Course,
    rule_set: CourseEligibilityRuleSet | None,
    *,
    source_mode: AcademicDataSourceMode,
    corequisite_status: str,
) -> bool:
    """Return authority for the complete course-information response.

    Section-level lifecycle and coverage fields still describe known course
    and prerequisite facts when the response is partial.  The top-level flag
    is deliberately stricter: unavailable corequisites, incomplete rules, or
    any unverified/unapproved rule prevent the complete response from being
    presented as authoritative.
    """

    return (
        source_mode is AcademicDataSourceMode.VERIFIED_AUTHORITATIVE
        and course.approval_status is ApprovalStatus.APPROVED
        and course.verification_status.is_source_verified
        and _course_rule_coverage_status(rule_set) == RuleSetStatus.COMPLETE.value
        and corequisite_status == "AVAILABLE"
        and rule_set is not None
        and bool(rule_set.rules)
        and all(
            rule.approval_status is ApprovalStatus.APPROVED
            for rule in rule_set.rules
        )
        and all(
            rule.verification_status.is_source_verified
            for rule in rule_set.rules
        )
    )


def _serialized_expression_contains_unsupported(
    expression: dict[str, Any],
) -> bool:
    if expression.get("supported") is False:
        return True
    children = expression.get("children")
    if isinstance(children, list) and any(
        _serialized_expression_contains_unsupported(child)
        for child in children
        if isinstance(child, dict)
    ):
        return True
    operand = expression.get("operand")
    return isinstance(operand, dict) and _serialized_expression_contains_unsupported(
        operand
    )


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
    "project_course_information",
    "project_degree_audit",
    "project_eligibility",
    "serialize_rule_expression",
]
