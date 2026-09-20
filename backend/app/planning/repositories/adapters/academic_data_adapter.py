"""Narrow JSON Academic Data Foundation adapter for course eligibility."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ...domain.course import Course, CourseIdentity, Program, Regulation
from ...domain.electives import ElectivePool
from ...domain.expressions import EntryRequirementExpression
from ...domain.eligibility import CourseEligibilityRuleSet, RuleSetStatus
from ...domain.errors import PlanningErrorCode
from ...domain.lifecycle import ApprovalStatus, VerificationStatus
from ...domain.provenance import Provenance
from ...domain.reasons import ReasonCode
from ...domain.rules import AcademicRule
from ...domain.requirements import (
    ProgramRequirement,
    ProgramRequirementSet,
    RequirementSetStatus,
    RequirementStage,
    requirement_stage as _requirement_stage,
)
from ...domain.uel import (
    UELMapping,
    UELMappingSet,
    UELModuleDefinition,
    UELModuleId,
    UELProgressCoverage,
)
from ...domain.version import DatasetVersion
from ...policy import ExecutionMode
from .academic_data_types import (
    AcademicDataConfig,
    AcademicDataDiagnostic,
    AcademicDataDiagnosticCode,
    AcademicDataLoadResult,
    AcademicDataLookup,
    AcademicDataSourceMode,
)
from .academic_expression_mapper import map_expression
from .academic_json_loader import (
    LoadedAcademicRecords,
    RawCourseRecord,
    RawAcademicRuleMetadata,
    RawPrerequisiteRecord,
    load_academic_records,
)
from .academic_requirement_mapper import map_elective_pool, map_program_requirement
from .eligibility_coverage import inspect_eligibility_coverage


@dataclass(frozen=True, slots=True)
class JsonAcademicDataAdapter:
    """Immutable indexed view over one Academic Data Foundation snapshot."""

    source_mode: AcademicDataSourceMode
    dataset_version: DatasetVersion | None
    _courses: tuple[tuple[CourseIdentity, Course], ...]
    _course_provenance: tuple[tuple[CourseIdentity, Provenance], ...]
    _prerequisites: tuple[RawPrerequisiteRecord, ...]
    _academic_rules: tuple[RawAcademicRuleMetadata, ...]
    _program_requirements: tuple[ProgramRequirement, ...]
    _elective_pools: tuple[ElectivePool, ...]
    _source_ids: frozenset[str]
    _diagnostics: tuple[AcademicDataDiagnostic, ...]
    _corequisites_loaded: bool
    _corequisite_count: int
    _uel_modules: tuple[UELModuleDefinition, ...] = ()
    _uel_mappings: UELMappingSet = UELMappingSet()
    _uel_module_coverage: UELProgressCoverage = UELProgressCoverage.UNAVAILABLE

    @classmethod
    def load(
        cls,
        config: AcademicDataConfig,
    ) -> AcademicDataLoadResult[JsonAcademicDataAdapter]:
        if not isinstance(config, AcademicDataConfig):
            raise TypeError("config must be an AcademicDataConfig")

        diagnostics: list[AcademicDataDiagnostic] = []
        if (
            config.requested_execution_mode is not None
            and config.requested_execution_mode is ExecutionMode.AUTHORITATIVE
            and config.source_mode is AcademicDataSourceMode.NORMALIZED_DEVELOPMENT
        ):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.DATASET_MODE_MISMATCH,
                    planning_code=PlanningErrorCode.UNAPPROVED_RULE,
                    reason_codes=(
                        ReasonCode.UNAPPROVED_RULE,
                        ReasonCode.UNVERIFIED_RULE,
                    ),
                    detail=(
                        "normalized development data cannot be selected for "
                        "authoritative execution"
                    ),
                    requires_human_review=True,
                )
            )
            return AcademicDataLoadResult(
                value=None,
                source_mode=config.source_mode,
                dataset_version=None,
                diagnostics=tuple(diagnostics),
            )

        source_root = config.package_root / (
            "normalized"
            if config.source_mode is AcademicDataSourceMode.NORMALIZED_DEVELOPMENT
            else "verified"
        )
        if not source_root.is_dir():
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.SOURCE_UNAVAILABLE,
                    planning_code=PlanningErrorCode.DATA_NOT_FOUND,
                    detail=str(source_root),
                    requires_human_review=True,
                )
            )
            return AcademicDataLoadResult(
                value=None,
                source_mode=config.source_mode,
                dataset_version=None,
                diagnostics=tuple(diagnostics),
            )

        records = load_academic_records(
            source_root,
            manifest_path=config.manifest_path,
        )
        adapter = cls._from_records(config.source_mode, records)
        diagnostics.extend(adapter._diagnostics)
        return AcademicDataLoadResult(
            value=adapter,
            source_mode=config.source_mode,
            dataset_version=adapter.dataset_version,
            diagnostics=_sorted_diagnostics(diagnostics),
        )

    @classmethod
    def _from_records(
        cls,
        source_mode: AcademicDataSourceMode,
        records: LoadedAcademicRecords,
    ) -> JsonAcademicDataAdapter:
        diagnostics = list(records.diagnostics)
        course_map: dict[CourseIdentity, Course] = {}
        provenance_map: dict[CourseIdentity, Provenance] = {}
        invalid_course_ids: set[str] = set()

        for raw in sorted(records.courses, key=lambda item: item.course_id):
            if _is_slot_record(raw.course_id):
                diagnostics.append(
                    _diagnostic(
                        AcademicDataDiagnosticCode.UNSUPPORTED_ENTITY_KIND,
                        planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
                        reason_codes=(ReasonCode.UNSUPPORTED_CASE,),
                        record_id=raw.course_id,
                        detail="elective slot records are not Course entities",
                    )
                )
                continue
            identity = _parse_course_identity(raw, diagnostics)
            if identity is None:
                continue
            if identity in course_map or identity.course_id in invalid_course_ids:
                course_map.pop(identity, None)
                provenance_map.pop(identity, None)
                invalid_course_ids.add(identity.course_id)
                diagnostics.append(
                    _diagnostic(
                        AcademicDataDiagnosticCode.DUPLICATE_RECORD,
                        planning_code=PlanningErrorCode.INVALID_REQUEST,
                        record_id=raw.course_id,
                        course_id=identity,
                        field="course_id",
                        requires_human_review=True,
                    )
                )
                continue
            mapped = _map_course(raw, identity, records.source_ids, diagnostics)
            if mapped is None:
                continue
            course, provenance = mapped
            course_map[identity] = course
            provenance_map[identity] = provenance

        mapped_requirements: list[ProgramRequirement] = []
        for raw in sorted(
            records.program_requirements,
            key=lambda item: item.requirement_id,
        ):
            mapped = map_program_requirement(raw, source_ids=records.source_ids)
            diagnostics.extend(mapped.diagnostics)
            if mapped.value is not None:
                mapped_requirements.append(mapped.value)

        mapped_pools: list[ElectivePool] = []
        for raw in sorted(records.elective_pools, key=lambda item: item.pool_id):
            mapped = map_elective_pool(
                raw,
                source_ids=records.source_ids,
                course_index=course_map,
            )
            diagnostics.extend(mapped.diagnostics)
            if mapped.value is not None:
                mapped_pools.append(mapped.value)

        uel_modules, uel_mappings, uel_module_coverage, uel_diagnostics = (
            _map_uel_records(
                records,
                source_ids=records.source_ids,
            )
        )
        diagnostics.extend(uel_diagnostics)

        return cls(
            source_mode=source_mode,
            dataset_version=records.dataset_version,
            _courses=tuple(
                sorted(course_map.items(), key=lambda item: item[0].course_id)
            ),
            _course_provenance=tuple(
                sorted(provenance_map.items(), key=lambda item: item[0].course_id)
            ),
            _prerequisites=tuple(
                sorted(
                    records.prerequisites, key=lambda item: item.prerequisite_rule_id
                )
            ),
            _academic_rules=tuple(
                sorted(records.academic_rules, key=lambda item: item.rule_id)
            ),
            _program_requirements=tuple(
                sorted(
                    mapped_requirements,
                    key=lambda requirement: requirement.requirement_id,
                )
            ),
            _elective_pools=tuple(
                sorted(mapped_pools, key=lambda pool: pool.pool_id.identifier)
            ),
            _source_ids=records.source_ids,
            _diagnostics=_sorted_diagnostics(diagnostics),
            _corequisites_loaded=records.corequisites_loaded,
            _corequisite_count=records.corequisite_count,
            _uel_modules=uel_modules,
            _uel_mappings=uel_mappings,
            _uel_module_coverage=uel_module_coverage,
        )

    @property
    def diagnostics(self) -> tuple[AcademicDataDiagnostic, ...]:
        return self._diagnostics

    @property
    def course_count(self) -> int:
        """Number of source records indexed as Planning ``Course`` values."""

        return len(self._courses)

    @property
    def corequisites_loaded(self) -> bool:
        return self._corequisites_loaded

    @property
    def corequisite_count(self) -> int:
        return self._corequisite_count

    @property
    def uel_module_count(self) -> int:
        """Number of typed UEL module definitions loaded from the snapshot."""

        return len(self._uel_modules)

    @property
    def uel_module_coverage(self) -> UELProgressCoverage:
        return self._uel_module_coverage

    def list_uel_modules(
        self,
        *,
        regulation: Regulation,
    ) -> tuple[UELModuleDefinition, ...]:
        if not isinstance(regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        return tuple(
            item for item in self._uel_modules if item.module.regulation is regulation
        )

    def get_uel_mapping_set(
        self,
        *,
        regulation: Regulation,
        program: Program,
    ) -> UELMappingSet:
        """Return scoped UEL mappings without upgrading source authority."""

        if not isinstance(regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(program, Program):
            raise TypeError("program must be a Program")
        mappings = tuple(
            item
            for item in self._uel_mappings.mappings
            if item.module.regulation is regulation and item.course.program == program
        )
        modules = tuple(
            item for item in self._uel_modules if item.module.regulation is regulation
        )
        return UELMappingSet(
            mappings=mappings,
            coverage=self._uel_mappings.coverage,
            modules=modules,
        )

    def list_requirements(
        self,
        *,
        regulation: Regulation,
        program: Program,
    ) -> tuple[ProgramRequirement, ...]:
        if not isinstance(regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(program, Program):
            raise TypeError("program must be a Program")
        return tuple(
            requirement
            for requirement in self._program_requirements
            if requirement.regulation is regulation and requirement.program == program
        )

    def list_elective_pools(
        self,
        *,
        regulation: Regulation,
        program: Program,
    ) -> tuple[ElectivePool, ...]:
        if not isinstance(regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(program, Program):
            raise TypeError("program must be a Program")
        return tuple(
            pool
            for pool in self._elective_pools
            if pool.pool_id.regulation is regulation and pool.pool_id.program == program
        )

    def get_requirement_set(
        self,
        *,
        regulation: Regulation,
        program: Program,
        stage: RequirementStage | None = None,
    ) -> ProgramRequirementSet:
        """Expose mapped requirements without claiming unsupported coverage.

        The current Academic Data package has no formal schema-backed
        requirement-set completeness signal.  Consequently this adapter keeps
        the set ``INCOMPLETE`` even when individual definitions are mapped.
        ``stage`` is applied only as a typed view; it does not upgrade source
        coverage.
        """

        requirements = self.list_requirements(
            regulation=regulation,
            program=program,
        )
        if stage is not None:
            requirements = tuple(
                item
                for item in requirements
                if item.definition is None
                or _requirement_stage(item.definition) is stage
            )
        provenance = tuple(
            item.provenance for item in requirements if item.provenance is not None
        )
        return ProgramRequirementSet(
            regulation=regulation,
            program=program,
            requirements=requirements,
            status=RequirementSetStatus.INCOMPLETE,
            dataset_version=self.dataset_version,
            provenance=provenance,
            reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
        )

    def get_course(
        self,
        course_id: CourseIdentity,
    ) -> AcademicDataLookup[Course]:
        if not isinstance(course_id, CourseIdentity):
            raise TypeError("course_id must be a CourseIdentity")
        for identity, course in self._courses:
            if identity == course_id:
                provenance = tuple(
                    item
                    for identity_value, item in self._course_provenance
                    if identity_value == course_id
                )
                return AcademicDataLookup(
                    value=course,
                    dataset_version=self.dataset_version,
                    provenance=provenance,
                    diagnostics=_diagnostics_for_course(self._diagnostics, course_id),
                )
        return AcademicDataLookup(
            value=None,
            dataset_version=self.dataset_version,
            diagnostics=(
                _diagnostic(
                    AcademicDataDiagnosticCode.COURSE_NOT_FOUND,
                    planning_code=PlanningErrorCode.DATA_NOT_FOUND,
                    course_id=course_id,
                    record_id=course_id.course_id,
                    requires_human_review=True,
                ),
            ),
        )

    def list_courses(
        self,
        *,
        regulation: Regulation,
        program: Program,
    ) -> tuple[Course, ...]:
        if not isinstance(regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(program, Program):
            raise TypeError("program must be a Program")
        return tuple(
            course
            for identity, course in self._courses
            if identity.regulation is regulation and identity.program == program
        )

    def get_eligibility_rules(
        self,
        course_id: CourseIdentity,
    ) -> AcademicDataLookup[CourseEligibilityRuleSet]:
        if not isinstance(course_id, CourseIdentity):
            raise TypeError("course_id must be a CourseIdentity")

        course_lookup = self.get_course(course_id)
        if course_lookup.value is None:
            return AcademicDataLookup(
                value=CourseEligibilityRuleSet(
                    target_course=course_id,
                    status=RuleSetStatus.UNAVAILABLE,
                    reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                ),
                dataset_version=self.dataset_version,
                diagnostics=course_lookup.diagnostics,
            )

        raw_rules = tuple(
            raw for raw in self._prerequisites if raw.course_id == course_id.course_id
        )
        diagnostics: list[AcademicDataDiagnostic] = []
        rules: list[AcademicRule] = []
        reason_codes: list[ReasonCode] = []
        incomplete = False
        raw_rule_ids = {raw.prerequisite_rule_id for raw in raw_rules}
        diagnostics.extend(
            item for item in self._diagnostics if item.record_id in raw_rule_ids
        )

        if not raw_rules:
            incomplete = True
            reason_codes.append(ReasonCode.MISSING_REQUIRED_DATA)
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.ELIGIBILITY_COVERAGE_GAP,
                    planning_code=PlanningErrorCode.DATA_NOT_FOUND,
                    reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                    course_id=course_id,
                    field="prerequisites",
                    detail=(
                        "No formal schema-backed no-prerequisite signal is "
                        "available for this course"
                    ),
                    requires_human_review=True,
                )
            )
        elif len(raw_rules) > 1:
            incomplete = True
            reason_codes.append(ReasonCode.MISSING_REQUIRED_DATA)
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.DUPLICATE_RULE,
                    planning_code=PlanningErrorCode.INVALID_REQUEST,
                    reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                    course_id=course_id,
                    record_id=course_id.course_id,
                    field="prerequisite_rule_id",
                    requires_human_review=True,
                )
            )
        else:
            mapped_rule, rule_diagnostics, rule_reasons, rule_incomplete = (
                self._map_prerequisite(raw_rules[0], course_id)
            )
            diagnostics.extend(rule_diagnostics)
            reason_codes.extend(rule_reasons)
            incomplete = incomplete or rule_incomplete
            if mapped_rule is not None:
                rules.append(mapped_rule)

        coverage_diagnostics = inspect_eligibility_coverage(
            course_id,
            self._academic_rules,
            academic_rules_available=_file_available(
                self._diagnostics,
                "academic_rules.json",
            ),
        )
        diagnostics.extend(coverage_diagnostics)
        if coverage_diagnostics:
            incomplete = True
            reason_codes.extend(
                reason
                for diagnostic in coverage_diagnostics
                for reason in diagnostic.reason_codes
            )

        corequisite_diagnostics = _corequisite_coverage_diagnostics(
            course_id,
            loaded=self._corequisites_loaded,
            count=self._corequisite_count,
        )
        diagnostics.extend(corequisite_diagnostics)
        if corequisite_diagnostics:
            incomplete = True
            reason_codes.extend(
                reason
                for diagnostic in corequisite_diagnostics
                for reason in diagnostic.reason_codes
            )

        status = RuleSetStatus.INCOMPLETE if incomplete else RuleSetStatus.COMPLETE
        rule_set = CourseEligibilityRuleSet(
            target_course=course_id,
            status=status,
            rules=tuple(rules),
            reason_codes=tuple(dict.fromkeys(reason_codes)),
        )
        provenance = tuple(
            rule.provenance for rule in rules if rule.provenance is not None
        )
        return AcademicDataLookup(
            value=rule_set,
            dataset_version=self.dataset_version,
            provenance=provenance,
            diagnostics=_sorted_diagnostics(diagnostics),
        )

    def _map_prerequisite(
        self,
        raw: RawPrerequisiteRecord,
        target: CourseIdentity,
    ) -> tuple[
        AcademicRule | None,
        tuple[AcademicDataDiagnostic, ...],
        tuple[ReasonCode, ...],
        bool,
    ]:
        diagnostics: list[AcademicDataDiagnostic] = []
        reasons: list[ReasonCode] = []
        incomplete = False
        try:
            regulation = Regulation.from_year(raw.regulation)
            program = Program(raw.program)
        except (TypeError, ValueError):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.RULE_TARGET_MISMATCH,
                    planning_code=PlanningErrorCode.INVALID_REQUEST,
                    record_id=raw.prerequisite_rule_id,
                    course_id=target,
                    requires_human_review=True,
                )
            )
            return None, tuple(diagnostics), (), True
        if (
            regulation is not target.regulation
            or program != target.program
            or raw.course_id != target.course_id
        ):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.RULE_TARGET_MISMATCH,
                    planning_code=PlanningErrorCode.INVALID_REQUEST,
                    record_id=raw.prerequisite_rule_id,
                    course_id=target,
                    requires_human_review=True,
                )
            )
            return None, tuple(diagnostics), (), True
        if raw.source_id not in self._source_ids:
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.UNKNOWN_SOURCE,
                    planning_code=PlanningErrorCode.DATA_NOT_FOUND,
                    reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                    record_id=raw.prerequisite_rule_id,
                    course_id=target,
                    source_id=raw.source_id,
                    requires_human_review=True,
                )
            )
            incomplete = True
        try:
            approval_status = ApprovalStatus.from_raw(raw.approval_status)
        except ValueError:
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.UNKNOWN_LIFECYCLE_VALUE,
                    planning_code=PlanningErrorCode.INVALID_REQUEST,
                    record_id=raw.prerequisite_rule_id,
                    field="approval_status",
                    requires_human_review=True,
                )
            )
            return None, tuple(diagnostics), (), True
        if raw.verification_status is None:
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.UNKNOWN_LIFECYCLE_VALUE,
                    planning_code=PlanningErrorCode.INVALID_REQUEST,
                    record_id=raw.prerequisite_rule_id,
                    field="verification_status",
                    requires_human_review=True,
                )
            )
            return None, tuple(diagnostics), (), True
        try:
            verification_status = VerificationStatus.from_raw(raw.verification_status)
        except ValueError:
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.UNKNOWN_LIFECYCLE_VALUE,
                    planning_code=PlanningErrorCode.INVALID_REQUEST,
                    record_id=raw.prerequisite_rule_id,
                    field="verification_status",
                    requires_human_review=True,
                )
            )
            return None, tuple(diagnostics), (), True
        if raw.critical_for_planner is None:
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.MISSING_REQUIRED_FIELD,
                    planning_code=PlanningErrorCode.INVALID_REQUEST,
                    record_id=raw.prerequisite_rule_id,
                    field="critical_for_planner",
                    requires_human_review=True,
                )
            )
            return None, tuple(diagnostics), (), True

        provenance = Provenance(
            rule_id=raw.prerequisite_rule_id,
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
                    record_id=raw.prerequisite_rule_id,
                    course_id=target,
                    source_id=raw.source_id,
                    conflict_ids=raw.conflict_ids,
                    requires_human_review=True,
                )
            )
            reasons.append(ReasonCode.CONFLICTED_RULE)
            incomplete = True
        if approval_status in {
            ApprovalStatus.BLOCKED,
            ApprovalStatus.CONFLICTED,
            ApprovalStatus.SUPERSEDED,
        }:
            reasons.append(
                ReasonCode.CONFLICTED_RULE
                if approval_status is ApprovalStatus.CONFLICTED
                else ReasonCode.BLOCKED_RULE
                if approval_status is ApprovalStatus.BLOCKED
                else ReasonCode.UNAPPROVED_RULE
            )
            incomplete = True
        if raw.rule_type != "PREREQUISITE":
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.UNSUPPORTED_EXPRESSION,
                    planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
                    reason_codes=(ReasonCode.UNSUPPORTED_RULE,),
                    record_id=raw.prerequisite_rule_id,
                    course_id=target,
                    source_type=raw.rule_type,
                    field="rule_type",
                    requires_human_review=True,
                )
            )
            reasons.append(ReasonCode.UNSUPPORTED_RULE)
            incomplete = True
        mapped_expression = map_expression(
            raw.expression,
            regulation=regulation,
            program=program,
            record_id=raw.prerequisite_rule_id,
        )
        diagnostics.extend(mapped_expression.diagnostics)
        if (
            mapped_expression.contains_unsupported
            or mapped_expression.expression is None
        ):
            reasons.append(ReasonCode.UNSUPPORTED_RULE)
            incomplete = True
        expression = mapped_expression.expression
        if expression is None:
            return None, tuple(diagnostics), tuple(dict.fromkeys(reasons)), True
        if isinstance(expression, EntryRequirementExpression):
            assert expression.reference is not None
            reasons.append(ReasonCode.ENTRY_REQUIREMENT_UNRESOLVED)
            expression = replace(
                expression,
                reference=replace(expression.reference, provenance=provenance),
            )
        return (
            AcademicRule(
                rule_id=raw.prerequisite_rule_id,
                regulation=regulation,
                program=program,
                approval_status=approval_status,
                verification_status=verification_status,
                critical_for_planner=raw.critical_for_planner,
                provenance=provenance,
                expression=expression,
            ),
            tuple(diagnostics),
            tuple(dict.fromkeys(reasons)),
            incomplete,
        )


def _parse_course_identity(
    raw: RawCourseRecord,
    diagnostics: list[AcademicDataDiagnostic],
) -> CourseIdentity | None:
    try:
        identity = CourseIdentity.parse(raw.course_id)
        regulation = Regulation.from_year(raw.regulation)
        program = Program(raw.program)
    except (TypeError, ValueError):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.MALFORMED_IDENTITY,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=raw.course_id,
                field="course_id",
                requires_human_review=True,
            )
        )
        return None
    if (
        identity.regulation is not regulation
        or identity.program != program
        or identity.course_code != raw.course_code
    ):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.MALFORMED_IDENTITY,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=raw.course_id,
                course_id=identity,
                field="regulation/program/course_code",
                requires_human_review=True,
            )
        )
        return None
    return identity


def _map_uel_records(
    records: LoadedAcademicRecords,
    *,
    source_ids: frozenset[str],
) -> tuple[
    tuple[UELModuleDefinition, ...],
    UELMappingSet,
    UELProgressCoverage,
    tuple[AcademicDataDiagnostic, ...],
]:
    diagnostics: list[AcademicDataDiagnostic] = []
    modules: dict[UELModuleId, UELModuleDefinition] = {}
    invalid_modules = False
    for raw in sorted(records.uel_modules, key=lambda item: item.uel_module_id):
        try:
            module = UELModuleId.parse(raw.uel_module_id)
            expected_regulation = Regulation.from_year(raw.regulation)
            approval_status = ApprovalStatus.from_raw(raw.approval_status)
            verification_status = (
                VerificationStatus.from_raw(raw.verification_status)
                if raw.verification_status is not None
                else None
            )
            if (
                module.regulation is not expected_regulation
                or module.module_code != raw.module_code
                or raw.source_id not in source_ids
                or verification_status is None
            ):
                raise ValueError("UEL module identity/source metadata mismatch")
            provenance = Provenance(
                rule_id=raw.uel_module_id,
                source_id=raw.source_id,
                source_page=raw.source_page,
                approval_status=approval_status,
                verification_status=verification_status,
            )
            mapped = UELModuleDefinition(
                module=module,
                module_name=raw.module_name,
                credits=raw.credits,
                provenance=provenance,
            )
        except (TypeError, ValueError):
            invalid_modules = True
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.SCHEMA_INVALID,
                    planning_code=PlanningErrorCode.INVALID_REQUEST,
                    record_id=raw.uel_module_id,
                    source_id=raw.source_id,
                    source_type="uel_module",
                    requires_human_review=True,
                )
            )
            continue
        if module in modules:
            invalid_modules = True
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.DUPLICATE_RECORD,
                    planning_code=PlanningErrorCode.INVALID_REQUEST,
                    record_id=raw.uel_module_id,
                    source_type="uel_module",
                    requires_human_review=True,
                )
            )
            continue
        if raw.conflict_ids:
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.CONFLICT_PRESENT,
                    planning_code=PlanningErrorCode.CONFLICTED_RULE,
                    reason_codes=(ReasonCode.CONFLICTED_RULE,),
                    record_id=raw.uel_module_id,
                    source_id=raw.source_id,
                    source_type="uel_module",
                    conflict_ids=raw.conflict_ids,
                    requires_human_review=True,
                )
            )
        modules[module] = mapped

    mapped: dict[str, UELMapping] = {}
    invalid_mappings = False
    for raw in sorted(records.uel_mappings, key=lambda item: item.mapping_id):
        try:
            module = UELModuleId.parse(raw.uel_module_id)
            expected_regulation = Regulation.from_year(raw.regulation)
            course = CourseIdentity.parse(raw.asu_course_id)
            approval_status = ApprovalStatus.from_raw(raw.approval_status)
            verification_status = (
                VerificationStatus.from_raw(raw.verification_status)
                if raw.verification_status is not None
                else None
            )
            if (
                module.regulation is not expected_regulation
                or course.regulation is not expected_regulation
                or str(course.program) != raw.asu_program
                or raw.source_id not in source_ids
                or verification_status is None
            ):
                raise ValueError("UEL mapping identity/source metadata mismatch")
            provenance = Provenance(
                rule_id=raw.mapping_id,
                source_id=raw.source_id,
                source_page=raw.source_page,
                approval_status=approval_status,
                verification_status=verification_status,
            )
            mapping = UELMapping(
                mapping_id=raw.mapping_id,
                module=module,
                course=course,
                mapping_type=raw.mapping_type,
                weight_percent=raw.weight_percent,
                provenance=provenance,
            )
        except (TypeError, ValueError):
            invalid_mappings = True
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.SCHEMA_INVALID,
                    planning_code=PlanningErrorCode.INVALID_REQUEST,
                    record_id=raw.mapping_id,
                    source_id=raw.source_id,
                    source_type="uel_mapping",
                    requires_human_review=True,
                )
            )
            continue
        if raw.mapping_id in mapped:
            invalid_mappings = True
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.DUPLICATE_RECORD,
                    planning_code=PlanningErrorCode.INVALID_REQUEST,
                    record_id=raw.mapping_id,
                    source_type="uel_mapping",
                    requires_human_review=True,
                )
            )
            continue
        if raw.conflict_ids:
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.CONFLICT_PRESENT,
                    planning_code=PlanningErrorCode.CONFLICTED_RULE,
                    reason_codes=(ReasonCode.CONFLICTED_RULE,),
                    record_id=raw.mapping_id,
                    course_id=course,
                    source_id=raw.source_id,
                    source_type="uel_mapping",
                    conflict_ids=raw.conflict_ids,
                    requires_human_review=True,
                )
            )
        mapped[raw.mapping_id] = mapping

    if not records.uel_mappings_available:
        mapping_coverage = UELProgressCoverage.UNAVAILABLE
    elif invalid_mappings:
        mapping_coverage = UELProgressCoverage.PARTIAL
    else:
        mapping_coverage = UELProgressCoverage.COMPLETE
    if not records.uel_modules_available:
        module_coverage = UELProgressCoverage.UNAVAILABLE
    elif invalid_modules:
        module_coverage = UELProgressCoverage.PARTIAL
    else:
        module_coverage = UELProgressCoverage.COMPLETE
    return (
        tuple(sorted(modules.values(), key=lambda item: str(item.module))),
        UELMappingSet(
            mappings=tuple(mapped.values()),
            coverage=mapping_coverage,
            modules=tuple(modules.values()),
        ),
        module_coverage,
        tuple(diagnostics),
    )


def _map_course(
    raw: RawCourseRecord,
    identity: CourseIdentity,
    source_ids: frozenset[str],
    diagnostics: list[AcademicDataDiagnostic],
) -> tuple[Course, Provenance] | None:
    try:
        approval_status = ApprovalStatus.from_raw(raw.approval_status)
    except ValueError:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.UNKNOWN_LIFECYCLE_VALUE,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=raw.course_id,
                field="approval_status",
                requires_human_review=True,
            )
        )
        return None
    if raw.verification_status is None:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.UNKNOWN_LIFECYCLE_VALUE,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=raw.course_id,
                field="verification_status",
                requires_human_review=True,
            )
        )
        return None
    try:
        verification_status = VerificationStatus.from_raw(raw.verification_status)
    except ValueError:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.UNKNOWN_LIFECYCLE_VALUE,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=raw.course_id,
                field="verification_status",
                requires_human_review=True,
            )
        )
        return None
    if raw.source_id not in source_ids:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.UNKNOWN_SOURCE,
                planning_code=PlanningErrorCode.DATA_NOT_FOUND,
                reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                record_id=raw.course_id,
                course_id=identity,
                source_id=raw.source_id,
                requires_human_review=True,
            )
        )
        return None
    if raw.conflict_ids:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.CONFLICT_PRESENT,
                planning_code=PlanningErrorCode.CONFLICTED_RULE,
                reason_codes=(ReasonCode.CONFLICTED_RULE,),
                record_id=raw.course_id,
                course_id=identity,
                source_id=raw.source_id,
                conflict_ids=raw.conflict_ids,
                requires_human_review=True,
            )
        )
        if approval_status not in {
            ApprovalStatus.BLOCKED,
            ApprovalStatus.CONFLICTED,
            ApprovalStatus.SUPERSEDED,
        }:
            return None
    try:
        course = Course(
            identity=identity,
            course_name=raw.course_name,
            credit_hours=raw.credit_hours,
            approval_status=approval_status,
            verification_status=verification_status,
        )
        provenance = Provenance(
            source_id=raw.source_id,
            source_page=raw.source_page,
            approval_status=approval_status,
            verification_status=verification_status,
        )
    except (TypeError, ValueError):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=raw.course_id,
                course_id=identity,
                requires_human_review=True,
            )
        )
        return None
    return course, provenance


def _is_slot_record(course_id: str) -> bool:
    return ":SLOT:" in course_id


def _file_available(
    diagnostics: tuple[AcademicDataDiagnostic, ...],
    filename: str,
) -> bool:
    return not any(
        item.detail is not None
        and Path(item.detail).name == filename
        and item.code
        in {
            AcademicDataDiagnosticCode.SOURCE_UNAVAILABLE,
            AcademicDataDiagnosticCode.SCHEMA_INVALID,
        }
        for item in diagnostics
    )


def _diagnostics_for_course(
    diagnostics: tuple[AcademicDataDiagnostic, ...],
    course_id: CourseIdentity,
) -> tuple[AcademicDataDiagnostic, ...]:
    return tuple(item for item in diagnostics if item.course_id == course_id)


def _corequisite_coverage_diagnostics(
    course_id: CourseIdentity,
    *,
    loaded: bool,
    count: int,
) -> tuple[AcademicDataDiagnostic, ...]:
    if loaded and count == 0:
        return ()
    detail = (
        "corequisite records exist but semester-aware corequisite semantics "
        "are outside this adapter slice"
        if loaded
        else "corequisites.json is unavailable"
    )
    return (
        _diagnostic(
            AcademicDataDiagnosticCode.ELIGIBILITY_COVERAGE_GAP,
            planning_code=(
                PlanningErrorCode.UNSUPPORTED_RULE
                if loaded
                else PlanningErrorCode.DATA_NOT_FOUND
            ),
            reason_codes=(
                ReasonCode.UNSUPPORTED_RULE
                if loaded
                else ReasonCode.MISSING_REQUIRED_DATA,
            ),
            course_id=course_id,
            source_type="corequisites",
            field="corequisites",
            detail=detail,
            requires_human_review=True,
        ),
    )


def _diagnostic(
    code: AcademicDataDiagnosticCode,
    *,
    planning_code: PlanningErrorCode = PlanningErrorCode.INVALID_REQUEST,
    reason_codes: tuple[ReasonCode, ...] = (),
    record_id: str | None = None,
    course_id: CourseIdentity | None = None,
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
        course_id=course_id,
        source_id=source_id,
        source_type=source_type,
        field=field,
        conflict_ids=conflict_ids,
        detail=detail,
        requires_human_review=requires_human_review,
    )


def _sorted_diagnostics(
    diagnostics: list[AcademicDataDiagnostic],
) -> tuple[AcademicDataDiagnostic, ...]:
    return tuple(
        sorted(
            diagnostics,
            key=lambda item: (
                item.code.value,
                item.record_id or "",
                item.field or "",
                item.source_type or "",
                item.detail or "",
            ),
        )
    )


AcademicDataAdapter = JsonAcademicDataAdapter
