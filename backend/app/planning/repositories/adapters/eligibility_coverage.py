"""Coverage checks for eligibility sources outside direct prerequisites."""

from __future__ import annotations

from ...domain.course import CourseIdentity, Program, Regulation
from ...domain.errors import PlanningErrorCode
from ...domain.lifecycle import ApprovalStatus, VerificationStatus
from ...domain.reasons import ReasonCode
from .academic_data_types import (
    AcademicDataDiagnostic,
    AcademicDataDiagnosticCode,
)
from .academic_json_loader import RawAcademicRuleMetadata


def inspect_eligibility_coverage(
    target_course: CourseIdentity,
    academic_rules: tuple[RawAcademicRuleMetadata, ...],
    *,
    academic_rules_available: bool,
) -> tuple[AcademicDataDiagnostic, ...]:
    """Report known eligibility sources not represented by this adapter slice."""

    if not academic_rules_available:
        return (
            AcademicDataDiagnostic(
                code=AcademicDataDiagnosticCode.ELIGIBILITY_COVERAGE_GAP,
                planning_code=PlanningErrorCode.DATA_NOT_FOUND,
                reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                course_id=target_course,
                source_type="academic_rules",
                field="eligibility_coverage",
                detail="academic_rules.json is unavailable",
                requires_human_review=True,
            ),
        )

    diagnostics: list[AcademicDataDiagnostic] = []
    for rule in academic_rules:
        if rule.rule_type != "GLOBAL_COURSE_PREREQUISITE":
            continue
        if not _scope_may_apply(rule, target_course):
            continue
        reason_codes = [ReasonCode.MISSING_REQUIRED_DATA]
        planning_code = PlanningErrorCode.UNSUPPORTED_RULE
        if rule.approval_status is None:
            reason_codes.append(ReasonCode.UNAPPROVED_RULE)
        else:
            try:
                approval_status = ApprovalStatus.from_raw(rule.approval_status)
            except ValueError:
                reason_codes.append(ReasonCode.UNAPPROVED_RULE)
                planning_code = PlanningErrorCode.INVALID_REQUEST
            else:
                if approval_status is not ApprovalStatus.APPROVED:
                    reason_codes.append(ReasonCode.UNAPPROVED_RULE)
                if approval_status is ApprovalStatus.BLOCKED:
                    reason_codes.append(ReasonCode.BLOCKED_RULE)
                    planning_code = PlanningErrorCode.UNAPPROVED_RULE
                elif approval_status is ApprovalStatus.CONFLICTED:
                    reason_codes.append(ReasonCode.CONFLICTED_RULE)
                    planning_code = PlanningErrorCode.CONFLICTED_RULE
                elif approval_status is ApprovalStatus.SUPERSEDED:
                    planning_code = PlanningErrorCode.UNAPPROVED_RULE
        if rule.verification_status != VerificationStatus.SOURCE_VERIFIED.value:
            reason_codes.append(ReasonCode.UNVERIFIED_RULE)
        diagnostics.append(
            AcademicDataDiagnostic(
                code=AcademicDataDiagnosticCode.ELIGIBILITY_COVERAGE_GAP,
                planning_code=planning_code,
                reason_codes=tuple(dict.fromkeys(reason_codes)),
                record_id=rule.rule_id,
                course_id=target_course,
                source_id=rule.source_id,
                source_type=rule.rule_type,
                field="eligibility_coverage",
                conflict_ids=rule.conflict_ids,
                detail=(
                    "A global course prerequisite may apply, but its "
                    "course-level applicability is outside this adapter slice"
                ),
                requires_human_review=True,
            )
        )
        if rule.conflict_ids:
            diagnostics.append(
                AcademicDataDiagnostic(
                    code=AcademicDataDiagnosticCode.CONFLICT_PRESENT,
                    planning_code=PlanningErrorCode.CONFLICTED_RULE,
                    reason_codes=(ReasonCode.CONFLICTED_RULE,),
                    record_id=rule.rule_id,
                    course_id=target_course,
                    source_id=rule.source_id,
                    source_type=rule.rule_type,
                    field="conflict_ids",
                    conflict_ids=rule.conflict_ids,
                    detail="eligibility-relevant global rule has active conflicts",
                    requires_human_review=True,
                )
            )
    return tuple(
        sorted(
            diagnostics,
            key=lambda item: (item.record_id or "", item.source_type or ""),
        )
    )


def _scope_may_apply(
    rule: RawAcademicRuleMetadata,
    target_course: CourseIdentity,
) -> bool:
    try:
        regulation = Regulation.from_year(rule.regulation)
        program = Program(rule.program)
    except (TypeError, ValueError):
        return True
    return regulation is target_course.regulation and (
        program == target_course.program or rule.program == "ALL_FOE"
    )
