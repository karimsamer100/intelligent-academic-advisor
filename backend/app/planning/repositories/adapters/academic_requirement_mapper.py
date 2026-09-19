"""Map the supported subset of Academic Data requirement records."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.course import Course, CourseIdentity, Program, Regulation
from ...domain.electives import (
    ElectivePool,
    ElectivePoolId,
    ElectivePoolType,
)
from ...domain.errors import PlanningErrorCode
from ...domain.lifecycle import ApprovalStatus, VerificationStatus
from ...domain.provenance import Provenance
from ...domain.reasons import ReasonCode
from ...domain.requirements import (
    ConcentrationRequirement,
    CourseCompletionRequirement,
    CourseCountFromPoolRequirement,
    ElectiveSlotRequirement,
    FieldTrainingRequirement,
    MinimumGPARequirement,
    ProgramRequirement,
    RequirementDefinition,
    TotalProgramCreditsRequirement,
    ZeroCreditCourseRequirement,
)
from ...domain.electives import ElectiveSlotId
from .academic_data_types import AcademicDataDiagnostic, AcademicDataDiagnosticCode
from .academic_json_loader import RawElectivePoolRecord, RawProgramRequirementRecord


@dataclass(frozen=True, slots=True)
class RequirementMappingResult:
    value: ProgramRequirement | None
    diagnostics: tuple[AcademicDataDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class PoolMappingResult:
    value: ElectivePool | None
    diagnostics: tuple[AcademicDataDiagnostic, ...] = ()


def map_program_requirement(
    raw: RawProgramRequirementRecord,
    *,
    source_ids: frozenset[str],
) -> RequirementMappingResult:
    diagnostics: list[AcademicDataDiagnostic] = []
    scope = _scope(raw.regulation, raw.program, raw.requirement_id, diagnostics)
    if scope is None:
        return RequirementMappingResult(None, tuple(diagnostics))
    regulation, program = scope
    lifecycle = _lifecycle(
        raw.approval_status,
        raw.verification_status,
        raw.requirement_id,
        diagnostics,
    )
    if lifecycle is None:
        return RequirementMappingResult(None, tuple(diagnostics))
    approval_status, verification_status = lifecycle
    if raw.source_id not in source_ids:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.UNKNOWN_SOURCE,
                planning_code=PlanningErrorCode.DATA_NOT_FOUND,
                reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                record_id=raw.requirement_id,
                source_id=raw.source_id,
                requires_human_review=True,
            )
        )
    provenance = Provenance(
        rule_id=raw.requirement_id,
        source_id=raw.source_id,
        source_page=raw.source_page,
        approval_status=approval_status,
        verification_status=verification_status,
    )
    if raw.conflict_ids:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.CONFLICT_PRESENT,
                planning_code=PlanningErrorCode.CONFLICTED_RULE,
                reason_codes=(ReasonCode.CONFLICTED_RULE,),
                record_id=raw.requirement_id,
                source_id=raw.source_id,
                conflict_ids=raw.conflict_ids,
                requires_human_review=True,
            )
        )

    definition = _definition(raw, regulation, program, diagnostics)
    requirement = ProgramRequirement(
        requirement_id=raw.requirement_id,
        regulation=regulation,
        program=program,
        approval_status=approval_status,
        verification_status=verification_status,
        provenance=provenance,
        definition=definition,
    )
    return RequirementMappingResult(requirement, tuple(diagnostics))


def map_elective_pool(
    raw: RawElectivePoolRecord,
    *,
    source_ids: frozenset[str],
    course_index: dict[CourseIdentity, Course],
) -> PoolMappingResult:
    diagnostics: list[AcademicDataDiagnostic] = []
    scope = _scope(raw.regulation, raw.program, raw.pool_id, diagnostics)
    if scope is None:
        return PoolMappingResult(None, tuple(diagnostics))
    regulation, program = scope
    pool_id = _scoped_id(raw.pool_id, regulation, program, ElectivePoolId)
    if pool_id is None:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.MALFORMED_IDENTITY,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=raw.pool_id,
                field="pool_id",
                requires_human_review=True,
            )
        )
        return PoolMappingResult(None, tuple(diagnostics))
    lifecycle = _lifecycle(
        raw.approval_status,
        raw.verification_status,
        raw.pool_id,
        diagnostics,
    )
    if lifecycle is None:
        return PoolMappingResult(None, tuple(diagnostics))
    approval_status, verification_status = lifecycle
    if raw.source_id not in source_ids:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.UNKNOWN_SOURCE,
                planning_code=PlanningErrorCode.DATA_NOT_FOUND,
                reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                record_id=raw.pool_id,
                source_id=raw.source_id,
                requires_human_review=True,
            )
        )
    if raw.conflict_ids:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.CONFLICT_PRESENT,
                planning_code=PlanningErrorCode.CONFLICTED_RULE,
                reason_codes=(ReasonCode.CONFLICTED_RULE,),
                record_id=raw.pool_id,
                source_id=raw.source_id,
                conflict_ids=raw.conflict_ids,
                requires_human_review=True,
            )
        )
    try:
        pool_type = ElectivePoolType(raw.pool_type)
    except ValueError:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.UNSUPPORTED_REQUIREMENT,
                planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
                reason_codes=(ReasonCode.UNSUPPORTED_RULE,),
                record_id=raw.pool_id,
                source_type=raw.pool_type,
                requires_human_review=True,
            )
        )
        return PoolMappingResult(None, tuple(diagnostics))
    allowed_courses: list[CourseIdentity] = []
    external_codes = list(raw.allowed_course_codes)
    for value in raw.allowed_courses:
        try:
            identity = CourseIdentity.parse(value)
        except ValueError:
            external_codes.append(value)
            continue
        if identity.regulation is not regulation or identity.program != program:
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.RULE_TARGET_MISMATCH,
                    planning_code=PlanningErrorCode.INVALID_REQUEST,
                    record_id=raw.pool_id,
                    detail=value,
                    requires_human_review=True,
                )
            )
            continue
        if identity not in course_index:
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.COURSE_NOT_FOUND,
                    planning_code=PlanningErrorCode.DATA_NOT_FOUND,
                    record_id=raw.pool_id,
                    detail=value,
                    requires_human_review=True,
                )
            )
        allowed_courses.append(identity)
    provenance = Provenance(
        source_id=raw.source_id,
        source_page=raw.source_page,
        approval_status=approval_status,
        verification_status=verification_status,
    )
    return PoolMappingResult(
        ElectivePool(
            pool_id=pool_id,
            pool_name=raw.pool_name,
            pool_type=pool_type,
            allowed_courses=tuple(dict.fromkeys(allowed_courses)),
            allowed_external_codes=tuple(dict.fromkeys(external_codes)),
            required_course_count=raw.required_number_of_courses,
            required_credit_hours=raw.required_credit_hours,
            approval_status=approval_status,
            verification_status=verification_status,
            provenance=provenance,
        ),
        tuple(diagnostics),
    )


def _definition(
    raw: RawProgramRequirementRecord,
    regulation: Regulation,
    program: Program,
    diagnostics: list[AcademicDataDiagnostic],
) -> RequirementDefinition | None:
    requirement_type = raw.requirement_type
    if requirement_type == "TOTAL_PROGRAM_CREDITS" and raw.min_value is not None:
        return TotalProgramCreditsRequirement(raw.min_value)
    if requirement_type == "MIN_GRADUATION_GPA" and raw.min_value is not None:
        return MinimumGPARequirement(raw.min_value)
    if requirement_type == "FIELD_TRAINING_WEEKS" and raw.min_value is not None:
        return FieldTrainingRequirement(int(raw.min_value))
    if requirement_type == "TECHNICAL_ELECTIVE_COUNT" and raw.min_courses is not None:
        pool_id = _pool_id(raw.elective_pool_id, regulation, program)
        if pool_id is not None:
            return CourseCountFromPoolRequirement(pool_id, raw.min_courses)
    if requirement_type == "CONCENTRATION_MIN_COURSES" and raw.min_courses is not None:
        pool_id = _pool_id(raw.elective_pool_id, regulation, program)
        if pool_id is not None:
            return ConcentrationRequirement(pool_id, raw.min_courses)
    if requirement_type == "ELECTIVE_SELECTION":
        slot_id = ElectiveSlotId(regulation, program, raw.requirement_id)
        pool_id = _pool_id(raw.elective_pool_id, regulation, program)
        return ElectiveSlotRequirement(slot_id, pool_id)
    if requirement_type == "ZERO_CREDIT_COMPLETION":
        if len(raw.required_courses) == 1:
            try:
                return ZeroCreditCourseRequirement(
                    CourseIdentity.parse(raw.required_courses[0])
                )
            except ValueError:
                pass
    if requirement_type == "COURSE_COMPLETION" and len(raw.required_courses) == 1:
        try:
            return CourseCompletionRequirement(
                CourseIdentity.parse(raw.required_courses[0])
            )
        except ValueError:
            pass
    if requirement_type not in {
        "TECHNICAL_ELECTIVE_CREDITS",
        "TECHNICAL_ELECTIVE_CREDITS_IMPLIED",
    }:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.UNSUPPORTED_REQUIREMENT,
                planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
                reason_codes=(ReasonCode.UNSUPPORTED_RULE,),
                record_id=raw.requirement_id,
                source_type=requirement_type,
                requires_human_review=True,
            )
        )
    return None


def _scope(
    regulation_value: int,
    program_value: str,
    record_id: str,
    diagnostics: list[AcademicDataDiagnostic],
) -> tuple[Regulation, Program] | None:
    try:
        return Regulation.from_year(regulation_value), Program(program_value)
    except (TypeError, ValueError):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.MALFORMED_IDENTITY,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=record_id,
                field="regulation/program",
                requires_human_review=True,
            )
        )
        return None


def _lifecycle(
    approval_value: str,
    verification_value: str | None,
    record_id: str,
    diagnostics: list[AcademicDataDiagnostic],
) -> tuple[ApprovalStatus, VerificationStatus] | None:
    try:
        approval = ApprovalStatus.from_raw(approval_value)
        verification = (
            VerificationStatus.from_raw(verification_value)
            if verification_value is not None
            else None
        )
    except ValueError:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.UNKNOWN_LIFECYCLE_VALUE,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=record_id,
                field="approval_status/verification_status",
                requires_human_review=True,
            )
        )
        return None
    if verification is None:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.UNKNOWN_LIFECYCLE_VALUE,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=record_id,
                field="verification_status",
                requires_human_review=True,
            )
        )
        return None
    return approval, verification


def _pool_id(
    value: str | None,
    regulation: Regulation,
    program: Program,
) -> ElectivePoolId | None:
    if value is None:
        return None
    return _scoped_id(value, regulation, program, ElectivePoolId)


def _scoped_id(
    value: str,
    regulation: Regulation,
    program: Program,
    identity_type: type[ElectivePoolId],
) -> ElectivePoolId | None:
    prefix = f"{regulation.value}:{program}:"
    if value.startswith(prefix):
        value = value[len(prefix) :]
    if not value:
        return None
    return identity_type(regulation, program, value)


def _diagnostic(
    code: AcademicDataDiagnosticCode,
    *,
    planning_code: PlanningErrorCode,
    reason_codes: tuple[ReasonCode, ...] = (),
    record_id: str | None = None,
    source_id: str | None = None,
    source_type: str | None = None,
    field: str | None = None,
    conflict_ids: tuple[str, ...] = (),
    detail: str | None = None,
    requires_human_review: bool = False,
) -> AcademicDataDiagnostic:
    return AcademicDataDiagnostic(
        code=code,
        planning_code=planning_code,
        reason_codes=reason_codes,
        record_id=record_id,
        source_id=source_id,
        source_type=source_type,
        field=field,
        conflict_ids=conflict_ids,
        detail=detail,
        requires_human_review=requires_human_review,
    )
