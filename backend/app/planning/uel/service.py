"""Deterministic UEL progress and risk evaluation."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..domain.reasons import ReasonCode
from ..domain.results import ResultMetadata
from ..domain.student import FactStatus, StudentState
from ..domain.trace import (
    DecisionStatus,
    DecisionTrace,
    DecisionTraceNode,
    TraceCode,
    TraceMetadata,
    TraceNodeType,
)
from ..domain.uel import (
    UELCoverage,
    UELMappingSet,
    UELModuleStatus,
    UELProgressCoverage,
    UELProgressEvaluationResult,
    UELProgressionRisk,
    UELRiskLevel,
    UELStudentProgress,
)
from ..domain.version import DatasetVersion
from ..policy import ExecutionMode, ExecutionPolicy


@dataclass(frozen=True, slots=True)
class UELProgressService:
    """Evaluate explicit UEL facts without deriving them from ASU outcomes."""

    dataset_version: DatasetVersion
    policy: ExecutionPolicy = ExecutionPolicy.development()

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_version, DatasetVersion):
            raise TypeError("dataset_version must be a DatasetVersion")
        if not isinstance(self.policy, ExecutionPolicy):
            raise TypeError("policy must be an ExecutionPolicy")

    def evaluate(
        self,
        *,
        student: StudentState | None,
        progress: UELStudentProgress,
        mappings: UELMappingSet,
    ) -> UELProgressEvaluationResult:
        if student is not None and not isinstance(student, StudentState):
            raise TypeError("student must be a StudentState or None")
        if not isinstance(progress, UELStudentProgress):
            raise TypeError("progress must be a UELStudentProgress")
        if not isinstance(mappings, UELMappingSet):
            raise TypeError("mappings must be a UELMappingSet")

        mapped_module_ids = {item.module for item in mappings.mappings} | {
            item.module for item in mappings.modules
        }
        missing_known_modules = mapped_module_ids - set(progress.known_modules)
        if missing_known_modules:
            progress = replace(
                progress,
                known_modules=(*progress.known_modules, *missing_known_modules),
            )

        risks: list[UELProgressionRisk] = []
        review = False
        reason_codes: list[ReasonCode] = []
        provenance = [
            item.provenance
            for item in progress.module_results
            if item.provenance is not None
        ]
        provenance.extend(
            item.provenance for item in mappings.mappings if item.provenance is not None
        )
        children: list[DecisionTraceNode] = []

        for module in progress.module_ids:
            result = progress.result_for(module)
            module_mappings = mappings.mappings_for_module(module)
            mapped_courses = mappings.courses_for_module(module)
            mapping_review = False
            mapping_reasons: tuple[ReasonCode, ...] = ()
            for mapping in module_mappings:
                decision = self.policy.assess(
                    mapping.provenance.approval_status
                    if mapping.provenance is not None
                    and mapping.provenance.approval_status is not None
                    else _blocked_approval(),
                    verification_status=(
                        mapping.provenance.verification_status
                        if mapping.provenance is not None
                        else None
                    ),
                    critical=True,
                )
                if not decision.allowed or (
                    self.policy.mode is ExecutionMode.AUTHORITATIVE
                    and not decision.authoritative
                ):
                    mapping_review = True
                    mapping_reasons = _unique_reasons(
                        (*mapping_reasons, *decision.reason_codes)
                    )

            level, reasons = self._risk_for(
                student,
                result,
                mapped_courses,
                mapping_review=mapping_review,
            )
            if level is UELRiskLevel.NONE:
                continue
            if mapping_review:
                level = UELRiskLevel.HUMAN_REVIEW_REQUIRED
                reasons = _unique_reasons(
                    (*reasons, *mapping_reasons, ReasonCode.UEL_MAPPING_UNSAFE)
                )
            if level is UELRiskLevel.UNKNOWN:
                reason_codes.append(ReasonCode.UEL_PROGRESS_UNKNOWN)
            elif level is UELRiskLevel.HUMAN_REVIEW_REQUIRED:
                review = True
                reason_codes.append(ReasonCode.UEL_REVIEW_REQUIRED)
            elif level is UELRiskLevel.PROGRESSION_RISK:
                reason_codes.append(ReasonCode.UEL_PROGRESSION_RISK)
            if result is not None:
                if result.status is UELModuleStatus.FAILED:
                    reason_codes.append(ReasonCode.UEL_MODULE_FAILED)
                if result.status is UELModuleStatus.OUTSTANDING:
                    reason_codes.append(ReasonCode.UEL_MODULE_OUTSTANDING)
                if result.requires_human_review:
                    review = True
                    level = UELRiskLevel.HUMAN_REVIEW_REQUIRED
                    reasons = _unique_reasons(
                        (*reasons, ReasonCode.UEL_REVIEW_REQUIRED)
                    )
            risk = UELProgressionRisk(
                module=module,
                level=level,
                mapped_courses=mapped_courses,
                reason_codes=reasons,
                provenance=tuple(
                    item.provenance
                    for item in module_mappings
                    if item.provenance is not None
                ),
            )
            risks.append(risk)
            children.append(
                DecisionTraceNode(
                    node_id=f"uel-risk:{module.module_id}",
                    code=TraceCode.UEL_RISK,
                    node_type=TraceNodeType.REQUIREMENT_CHECK,
                    status=_trace_status(level),
                    subject=module.module_id,
                    actual_value=level.value,
                    reason_codes=tuple(
                        reason for reason in reasons if isinstance(reason, ReasonCode)
                    ),
                    provenance=risk.provenance,
                    metadata=(
                        TraceMetadata("mapped_course_count", len(mapped_courses)),
                    ),
                )
            )

        if progress.coverage is not UELProgressCoverage.COMPLETE:
            review = True
            reason_codes.append(ReasonCode.UEL_PROGRESS_INCOMPLETE)
        facts_have_provenance = all(
            (result := progress.result_for(module)) is not None
            and result.provenance is not None
            for module in progress.module_ids
        )
        if (
            self.policy.mode is ExecutionMode.AUTHORITATIVE
            and not facts_have_provenance
        ):
            review = True
            reason_codes.append(ReasonCode.UEL_PROGRESS_UNVERIFIED)
        if mappings.coverage is not UELProgressCoverage.COMPLETE:
            review = True
            reason_codes.append(ReasonCode.UEL_MAPPING_INCOMPLETE)

        trace = DecisionTrace(
            DecisionTraceNode(
                node_id="uel-progress",
                code=TraceCode.UEL_PROGRESS,
                node_type=TraceNodeType.ROOT,
                status=(
                    DecisionStatus.ADVISOR_REVIEW
                    if review
                    else DecisionStatus.SATISFIED
                ),
                expected_value=UELProgressCoverage.COMPLETE.value,
                actual_value=progress.coverage.value,
                children=tuple(children),
                provenance=tuple(dict.fromkeys(provenance)),
                metadata=(
                    TraceMetadata("mapping_coverage", mappings.coverage.value),
                    TraceMetadata("risk_count", len(risks)),
                ),
            )
        )
        unique_reasons = _unique_reasons(tuple(reason_codes))
        authoritative = (
            self.policy.mode is ExecutionMode.AUTHORITATIVE
            and progress.coverage is UELProgressCoverage.COMPLETE
            and mappings.coverage is UELProgressCoverage.COMPLETE
            and not review
            and facts_have_provenance
            and all(
                item.provenance
                and item.provenance.approval_status is not None
                and item.provenance.verification_status is not None
                for item in mappings.mappings
            )
        )
        metadata = ResultMetadata(
            dataset_version=self.dataset_version,
            execution_mode=self.policy.mode,
            authoritative=authoritative,
            reason_codes=unique_reasons,
            provenance=tuple(dict.fromkeys(provenance)),
            decision_trace=trace,
            requires_human_review=review,
        )
        coverage = UELCoverage(
            mapping=mappings.coverage,
            module_facts=progress.coverage,
            evaluation=(
                UELProgressCoverage.PARTIAL if review else UELProgressCoverage.COMPLETE
            ),
        )
        return UELProgressEvaluationResult(
            progress=progress,
            mappings=mappings,
            coverage=coverage,
            risks=tuple(risks),
            metadata=metadata,
            trace=trace,
        )

    def _risk_for(
        self,
        student: StudentState | None,
        result,
        mapped_courses,
        *,
        mapping_review: bool,
    ) -> tuple[UELRiskLevel, tuple[ReasonCode, ...]]:
        if not mapped_courses:
            return UELRiskLevel.NONE, ()
        if mapping_review:
            return UELRiskLevel.HUMAN_REVIEW_REQUIRED, (ReasonCode.UEL_MAPPING_UNSAFE,)
        if result is None or result.status is UELModuleStatus.UNKNOWN:
            return UELRiskLevel.UNKNOWN, (ReasonCode.UEL_PROGRESS_UNKNOWN,)
        if result.requires_human_review:
            return UELRiskLevel.HUMAN_REVIEW_REQUIRED, (ReasonCode.UEL_REVIEW_REQUIRED,)
        if result.status is UELModuleStatus.PASSED:
            return UELRiskLevel.NONE, ()
        if result.status is UELModuleStatus.IN_PROGRESS:
            return UELRiskLevel.ATTENTION, (ReasonCode.UEL_MODULE_IN_PROGRESS,)
        if result.status is UELModuleStatus.FAILED:
            if student is not None and all(
                student.pass_status(course) is FactStatus.KNOWN_TRUE
                for course in mapped_courses
            ):
                return UELRiskLevel.ATTENTION, (ReasonCode.UEL_MODULE_FAILED,)
            return UELRiskLevel.PROGRESSION_RISK, (ReasonCode.UEL_MODULE_FAILED,)
        if result.status is UELModuleStatus.OUTSTANDING:
            if student is not None and all(
                student.pass_status(course) is FactStatus.KNOWN_TRUE
                for course in mapped_courses
            ):
                return UELRiskLevel.ATTENTION, (ReasonCode.UEL_MODULE_OUTSTANDING,)
            return UELRiskLevel.PROGRESSION_RISK, (ReasonCode.UEL_MODULE_OUTSTANDING,)
        return UELRiskLevel.UNKNOWN, (ReasonCode.UEL_PROGRESS_UNKNOWN,)


def _blocked_approval():
    from ..domain.lifecycle import ApprovalStatus

    return ApprovalStatus.BLOCKED


def _unique_reasons(reasons):
    return tuple(dict.fromkeys(reasons))


def _trace_status(level: UELRiskLevel) -> DecisionStatus:
    return {
        UELRiskLevel.NONE: DecisionStatus.SATISFIED,
        UELRiskLevel.ATTENTION: DecisionStatus.CONDITIONAL,
        UELRiskLevel.PROGRESSION_RISK: DecisionStatus.FAILED,
        UELRiskLevel.HUMAN_REVIEW_REQUIRED: DecisionStatus.ADVISOR_REVIEW,
        UELRiskLevel.UNKNOWN: DecisionStatus.INDETERMINATE,
    }[level]


__all__ = ["UELProgressService"]
