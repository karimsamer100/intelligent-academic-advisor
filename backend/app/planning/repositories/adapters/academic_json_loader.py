"""Private JSON loading and validation for the Academic Data adapter."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...domain.course import CourseIdentity
from ...domain.errors import PlanningErrorCode
from ...domain.reasons import ReasonCode
from ...domain.version import DatasetVersion
from .academic_data_types import (
    AcademicDataDiagnostic,
    AcademicDataDiagnosticCode,
)


@dataclass(frozen=True, slots=True)
class RawExpression:
    """Small typed projection of source expression fields used by mapping."""

    source_type: str
    conditions: tuple[RawExpression, ...] = ()
    course_id: str | None = None
    course_code: str | None = None
    code: str | None = None
    value: int | float | str | bool | None = None
    condition_note: str | None = None
    reason: str | None = None
    external_reference: bool | None = None


@dataclass(frozen=True, slots=True)
class RawCourseRecord:
    course_id: str
    regulation: int
    program: str
    course_code: str
    course_name: str
    credit_hours: int | float
    source_id: str
    source_page: int | str | None
    verification_status: str | None
    approval_status: str
    conflict_ids: tuple[str, ...]
    planner_usable: bool | None
    course_type: str | None


@dataclass(frozen=True, slots=True)
class RawPrerequisiteRecord:
    prerequisite_rule_id: str
    course_id: str
    regulation: int
    program: str
    rule_type: str
    expression: RawExpression | None
    source_id: str
    source_page: int | str | None
    verification_status: str | None
    approval_status: str
    conflict_ids: tuple[str, ...]
    critical_for_planner: bool | None


@dataclass(frozen=True, slots=True)
class RawAcademicRuleMetadata:
    rule_id: str
    regulation: int
    program: str
    rule_type: str
    course_scope: str | None
    source_id: str | None
    verification_status: str | None
    approval_status: str | None
    conflict_ids: tuple[str, ...]
    critical_for_planner: bool | None


@dataclass(frozen=True, slots=True)
class RawProgramRequirementRecord:
    requirement_id: str
    regulation: int
    program: str
    requirement_type: str
    requirement_group: str
    required_courses: tuple[str, ...]
    required_credit_hours: int | float | None
    min_value: int | float | None
    min_courses: int | None
    elective_pool_id: str | None
    source_id: str
    source_page: int | str | None
    verification_status: str | None
    approval_status: str
    conflict_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RawElectivePoolRecord:
    pool_id: str
    regulation: int
    program: str
    pool_name: str
    pool_type: str
    allowed_courses: tuple[str, ...]
    allowed_course_codes: tuple[str, ...]
    required_number_of_courses: int | None
    required_credit_hours: int | float | None
    source_id: str
    source_page: int | str | None
    verification_status: str | None
    approval_status: str
    conflict_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RawUELModuleRecord:
    uel_module_id: str
    regulation: int
    asu_program: str
    module_code: str
    module_name: str
    credits: int | float
    source_id: str
    source_page: int | str | None
    verification_status: str | None
    approval_status: str
    conflict_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RawUELMappingRecord:
    mapping_id: str
    regulation: int
    uel_module_id: str
    asu_program: str
    asu_course_id: str
    mapping_type: str
    weight_percent: int | float | None
    source_id: str
    source_page: int | str | None
    verification_status: str | None
    approval_status: str
    conflict_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LoadedAcademicRecords:
    courses: tuple[RawCourseRecord, ...]
    prerequisites: tuple[RawPrerequisiteRecord, ...]
    academic_rules: tuple[RawAcademicRuleMetadata, ...]
    program_requirements: tuple[RawProgramRequirementRecord, ...]
    elective_pools: tuple[RawElectivePoolRecord, ...]
    source_ids: frozenset[str]
    corequisites_loaded: bool
    corequisite_count: int
    dataset_version: DatasetVersion | None
    diagnostics: tuple[AcademicDataDiagnostic, ...]
    uel_modules: tuple[RawUELModuleRecord, ...] = ()
    uel_mappings: tuple[RawUELMappingRecord, ...] = ()
    uel_modules_available: bool = False
    uel_mappings_available: bool = False


def load_academic_records(
    source_root: Path,
    *,
    manifest_path: Path | None = None,
) -> LoadedAcademicRecords:
    diagnostics: list[AcademicDataDiagnostic] = []
    source_ids = _load_source_ids(source_root / "source_registry.json", diagnostics)
    courses = _load_courses(source_root / "courses.json", diagnostics)
    prerequisites = _load_prerequisites(source_root / "prerequisites.json", diagnostics)
    corequisites_loaded, corequisite_count = _load_corequisites(
        source_root / "corequisites.json", diagnostics
    )
    academic_rules = _load_academic_rule_metadata(
        source_root / "academic_rules.json", diagnostics
    )
    program_requirements = _load_program_requirements(
        source_root / "program_requirements.json", diagnostics
    )
    elective_pools = _load_elective_pools(
        source_root / "elective_pools.json", diagnostics
    )
    uel_modules, uel_modules_available = _load_uel_modules(
        source_root / "uel_modules.json", diagnostics
    )
    uel_mappings, uel_mappings_available = _load_uel_mappings(
        source_root / "uel_asu_mapping.json", diagnostics
    )
    dataset_version = _load_manifest(
        manifest_path or source_root / "dataset_manifest.json",
        diagnostics,
    )
    return LoadedAcademicRecords(
        courses=tuple(courses),
        prerequisites=tuple(prerequisites),
        academic_rules=tuple(academic_rules),
        program_requirements=tuple(program_requirements),
        elective_pools=tuple(elective_pools),
        source_ids=frozenset(source_ids),
        corequisites_loaded=corequisites_loaded,
        corequisite_count=corequisite_count,
        dataset_version=dataset_version,
        diagnostics=_sorted_diagnostics(diagnostics),
        uel_modules=tuple(uel_modules),
        uel_mappings=tuple(uel_mappings),
        uel_modules_available=uel_modules_available,
        uel_mappings_available=uel_mappings_available,
    )


def _load_source_ids(
    path: Path,
    diagnostics: list[AcademicDataDiagnostic],
) -> set[str]:
    values = _read_array(path, diagnostics)
    source_ids: set[str] = set()
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.SCHEMA_INVALID,
                    record_id=f"source[{index}]",
                    field="record",
                )
            )
            continue
        source_id = _required_string(
            value,
            "source_id",
            diagnostics,
            record_id=f"source[{index}]",
        )
        if source_id is not None:
            if source_id in source_ids:
                diagnostics.append(
                    _diagnostic(
                        AcademicDataDiagnosticCode.DUPLICATE_RECORD,
                        record_id=source_id,
                        field="source_id",
                    )
                )
            source_ids.add(source_id)
    return source_ids


def _load_courses(
    path: Path,
    diagnostics: list[AcademicDataDiagnostic],
) -> list[RawCourseRecord]:
    values = _read_array(path, diagnostics)
    records: list[RawCourseRecord] = []
    for index, value in enumerate(values):
        record_id = f"course[{index}]"
        if not isinstance(value, dict):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.SCHEMA_INVALID,
                    record_id=record_id,
                    field="record",
                )
            )
            continue
        course_id = _required_string(
            value, "course_id", diagnostics, record_id=record_id
        )
        regulation = _required_integer(
            value, "regulation", diagnostics, record_id=record_id
        )
        program = _required_string(value, "program", diagnostics, record_id=record_id)
        course_code = _required_string(
            value, "course_code", diagnostics, record_id=record_id
        )
        course_name = _required_string(
            value, "course_name", diagnostics, record_id=record_id
        )
        credit_hours = _required_number(
            value, "credit_hours", diagnostics, record_id=record_id
        )
        source_id = _required_string(
            value, "source_id", diagnostics, record_id=record_id
        )
        approval_status = _required_string(
            value, "approval_status", diagnostics, record_id=record_id
        )
        if None in (
            course_id,
            regulation,
            program,
            course_code,
            course_name,
            credit_hours,
            source_id,
            approval_status,
        ):
            continue
        verification_status = _optional_string(
            value, "verification_status", diagnostics, record_id
        )
        course_type = _optional_string(value, "course_type", diagnostics, record_id)
        source_page = _source_page(value, diagnostics, record_id)
        conflict_ids = _conflict_ids(value, diagnostics, record_id)
        planner_usable = _optional_bool(value, "planner_usable", diagnostics, record_id)
        records.append(
            RawCourseRecord(
                course_id=course_id,
                regulation=regulation,
                program=program,
                course_code=course_code,
                course_name=course_name,
                credit_hours=credit_hours,
                source_id=source_id,
                source_page=source_page,
                verification_status=verification_status,
                approval_status=approval_status,
                conflict_ids=conflict_ids,
                planner_usable=planner_usable,
                course_type=course_type,
            )
        )
    return records


def _load_prerequisites(
    path: Path,
    diagnostics: list[AcademicDataDiagnostic],
) -> list[RawPrerequisiteRecord]:
    values = _read_array(path, diagnostics)
    records: list[RawPrerequisiteRecord] = []
    for index, value in enumerate(values):
        record_id = f"prerequisite[{index}]"
        if not isinstance(value, dict):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.SCHEMA_INVALID,
                    record_id=record_id,
                    field="record",
                )
            )
            continue
        rule_id = _required_string(
            value, "prerequisite_rule_id", diagnostics, record_id=record_id
        )
        course_id = _required_string(
            value, "course_id", diagnostics, record_id=record_id
        )
        regulation = _required_integer(
            value, "regulation", diagnostics, record_id=record_id
        )
        program = _required_string(value, "program", diagnostics, record_id=record_id)
        rule_type = _required_string(
            value, "rule_type", diagnostics, record_id=record_id
        )
        source_id = _required_string(
            value, "source_id", diagnostics, record_id=record_id
        )
        approval_status = _required_string(
            value, "approval_status", diagnostics, record_id=record_id
        )
        if None in (
            rule_id,
            course_id,
            regulation,
            program,
            rule_type,
            source_id,
            approval_status,
        ):
            continue
        expression = _parse_expression(
            value.get("expression"),
            diagnostics,
            record_id=rule_id,
        )
        source_page = _source_page(value, diagnostics, rule_id)
        verification_status = _optional_string(
            value, "verification_status", diagnostics, rule_id
        )
        conflict_ids = _conflict_ids(value, diagnostics, rule_id)
        critical_for_planner = _optional_bool(
            value, "critical_for_planner", diagnostics, rule_id
        )
        records.append(
            RawPrerequisiteRecord(
                prerequisite_rule_id=rule_id,
                course_id=course_id,
                regulation=regulation,
                program=program,
                rule_type=rule_type,
                expression=expression,
                source_id=source_id,
                source_page=source_page,
                verification_status=verification_status,
                approval_status=approval_status,
                conflict_ids=conflict_ids,
                critical_for_planner=critical_for_planner,
            )
        )
    return records


def _load_corequisites(
    path: Path,
    diagnostics: list[AcademicDataDiagnostic],
) -> tuple[bool, int]:
    values = _read_array(path, diagnostics)
    return path.is_file() and not _has_source_unavailable(diagnostics, path), len(
        values
    )


def _load_academic_rule_metadata(
    path: Path,
    diagnostics: list[AcademicDataDiagnostic],
) -> list[RawAcademicRuleMetadata]:
    values = _read_array(path, diagnostics)
    records: list[RawAcademicRuleMetadata] = []
    for index, value in enumerate(values):
        record_id = f"academic-rule[{index}]"
        if not isinstance(value, dict):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.SCHEMA_INVALID,
                    record_id=record_id,
                    field="record",
                )
            )
            continue
        rule_id = _required_string(value, "rule_id", diagnostics, record_id=record_id)
        regulation = _required_integer(
            value, "regulation", diagnostics, record_id=record_id
        )
        program = _required_string(value, "program", diagnostics, record_id=record_id)
        rule_type = _required_string(
            value, "rule_type", diagnostics, record_id=record_id
        )
        if None in (rule_id, regulation, program, rule_type):
            continue
        conditions = value.get("conditions")
        if conditions is not None and not isinstance(conditions, dict):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.SCHEMA_INVALID,
                    record_id=rule_id,
                    field="conditions",
                )
            )
            continue
        source_id = _optional_string(value, "source_id", diagnostics, rule_id)
        verification_status = _optional_string(
            value, "verification_status", diagnostics, rule_id
        )
        approval_status = _optional_string(
            value, "approval_status", diagnostics, rule_id
        )
        conflict_ids = _conflict_ids(value, diagnostics, rule_id)
        critical_for_planner = _optional_bool(
            value, "critical_for_planner", diagnostics, rule_id
        )
        course_scope = None
        if isinstance(conditions, dict):
            raw_scope = conditions.get("course_scope")
            if raw_scope is not None and not isinstance(raw_scope, str):
                diagnostics.append(
                    _diagnostic(
                        AcademicDataDiagnosticCode.SCHEMA_INVALID,
                        record_id=rule_id,
                        field="conditions.course_scope",
                    )
                )
                continue
            course_scope = raw_scope
        records.append(
            RawAcademicRuleMetadata(
                rule_id=rule_id,
                regulation=regulation,
                program=program,
                rule_type=rule_type,
                course_scope=course_scope,
                source_id=source_id,
                verification_status=verification_status,
                approval_status=approval_status,
                conflict_ids=conflict_ids,
                critical_for_planner=critical_for_planner,
            )
        )
    return records


def _load_program_requirements(
    path: Path,
    diagnostics: list[AcademicDataDiagnostic],
) -> list[RawProgramRequirementRecord]:
    values = _read_array(path, diagnostics)
    records: list[RawProgramRequirementRecord] = []
    for index, value in enumerate(values):
        record_id = f"program-requirement[{index}]"
        if not isinstance(value, dict):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.SCHEMA_INVALID,
                    record_id=record_id,
                    field="record",
                )
            )
            continue
        requirement_id = _required_string(
            value, "requirement_id", diagnostics, record_id=record_id
        )
        regulation = _required_integer(
            value, "regulation", diagnostics, record_id=record_id
        )
        program = _required_string(value, "program", diagnostics, record_id=record_id)
        requirement_type = _required_string(
            value, "requirement_type", diagnostics, record_id=record_id
        )
        requirement_group = _required_string(
            value, "requirement_group", diagnostics, record_id=record_id
        )
        source_id = _required_string(
            value, "source_id", diagnostics, record_id=record_id
        )
        approval_status = _required_string(
            value, "approval_status", diagnostics, record_id=record_id
        )
        if None in (
            requirement_id,
            regulation,
            program,
            requirement_type,
            requirement_group,
            source_id,
            approval_status,
        ):
            continue
        required_courses = _string_tuple(
            value.get("required_courses"),
            diagnostics,
            record_id=requirement_id,
            field="required_courses",
        )
        required_credit_hours = _optional_number_field(
            value.get("required_credit_hours"),
            diagnostics,
            record_id=requirement_id,
            field="required_credit_hours",
        )
        min_value = _optional_number_field(
            value.get("min_value"),
            diagnostics,
            record_id=requirement_id,
            field="min_value",
        )
        min_courses = _optional_integer_field(
            value.get("min_courses"),
            diagnostics,
            record_id=requirement_id,
            field="min_courses",
        )
        elective_pool_id = _optional_string(
            value, "elective_pool_id", diagnostics, requirement_id
        )
        records.append(
            RawProgramRequirementRecord(
                requirement_id=requirement_id,
                regulation=regulation,
                program=program,
                requirement_type=requirement_type,
                requirement_group=requirement_group,
                required_courses=required_courses,
                required_credit_hours=required_credit_hours,
                min_value=min_value,
                min_courses=min_courses,
                elective_pool_id=elective_pool_id,
                source_id=source_id,
                source_page=_source_page(value, diagnostics, requirement_id),
                verification_status=_optional_string(
                    value, "verification_status", diagnostics, requirement_id
                ),
                approval_status=approval_status,
                conflict_ids=_conflict_ids(value, diagnostics, requirement_id),
            )
        )
    return records


def _load_elective_pools(
    path: Path,
    diagnostics: list[AcademicDataDiagnostic],
) -> list[RawElectivePoolRecord]:
    values = _read_array(path, diagnostics)
    records: list[RawElectivePoolRecord] = []
    for index, value in enumerate(values):
        record_id = f"elective-pool[{index}]"
        if not isinstance(value, dict):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.SCHEMA_INVALID,
                    record_id=record_id,
                    field="record",
                )
            )
            continue
        pool_id = _required_string(value, "pool_id", diagnostics, record_id=record_id)
        regulation = _required_integer(
            value, "regulation", diagnostics, record_id=record_id
        )
        program = _required_string(value, "program", diagnostics, record_id=record_id)
        pool_name = _required_string(
            value, "pool_name", diagnostics, record_id=record_id
        )
        source_id = _required_string(
            value, "source_id", diagnostics, record_id=record_id
        )
        approval_status = _required_string(
            value, "approval_status", diagnostics, record_id=record_id
        )
        if None in (
            pool_id,
            regulation,
            program,
            pool_name,
            source_id,
            approval_status,
        ):
            continue
        pool_type = _optional_string(value, "pool_type", diagnostics, pool_id)
        records.append(
            RawElectivePoolRecord(
                pool_id=pool_id,
                regulation=regulation,
                program=program,
                pool_name=pool_name,
                pool_type=pool_type or "UNKNOWN",
                allowed_courses=_string_tuple(
                    value.get("allowed_courses"),
                    diagnostics,
                    record_id=pool_id,
                    field="allowed_courses",
                ),
                allowed_course_codes=_string_tuple(
                    value.get("allowed_course_codes"),
                    diagnostics,
                    record_id=pool_id,
                    field="allowed_course_codes",
                ),
                required_number_of_courses=_optional_integer_field(
                    value.get("required_number_of_courses"),
                    diagnostics,
                    record_id=pool_id,
                    field="required_number_of_courses",
                ),
                required_credit_hours=_optional_number_field(
                    value.get("required_credit_hours"),
                    diagnostics,
                    record_id=pool_id,
                    field="required_credit_hours",
                ),
                source_id=source_id,
                source_page=_source_page(value, diagnostics, pool_id),
                verification_status=_optional_string(
                    value, "verification_status", diagnostics, pool_id
                ),
                approval_status=approval_status,
                conflict_ids=_conflict_ids(value, diagnostics, pool_id),
            )
        )
    return records


def _load_uel_modules(
    path: Path,
    diagnostics: list[AcademicDataDiagnostic],
) -> tuple[list[RawUELModuleRecord], bool]:
    values, available = _read_optional_array(path, diagnostics)
    records: list[RawUELModuleRecord] = []
    for index, value in enumerate(values):
        record_id = f"uel-module[{index}]"
        if not isinstance(value, dict):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.SCHEMA_INVALID,
                    record_id=record_id,
                    field="record",
                )
            )
            continue
        uel_module_id = _required_string(
            value, "uel_module_id", diagnostics, record_id=record_id
        )
        regulation = _required_integer(
            value, "regulation", diagnostics, record_id=record_id
        )
        asu_program = _required_string(
            value, "asu_program", diagnostics, record_id=record_id
        )
        module_code = _required_string(
            value, "module_code", diagnostics, record_id=record_id
        )
        module_name = _required_string(
            value, "module_name", diagnostics, record_id=record_id
        )
        credits = _required_number(value, "credits", diagnostics, record_id=record_id)
        source_id = _required_string(
            value, "source_id", diagnostics, record_id=record_id
        )
        approval_status = _required_string(
            value, "approval_status", diagnostics, record_id=record_id
        )
        if None in (
            uel_module_id,
            regulation,
            asu_program,
            module_code,
            module_name,
            credits,
            source_id,
            approval_status,
        ):
            continue
        records.append(
            RawUELModuleRecord(
                uel_module_id=uel_module_id,
                regulation=regulation,
                asu_program=asu_program,
                module_code=module_code,
                module_name=module_name,
                credits=credits,
                source_id=source_id,
                source_page=_source_page(value, diagnostics, record_id),
                verification_status=_optional_string(
                    value, "verification_status", diagnostics, record_id
                ),
                approval_status=approval_status,
                conflict_ids=_conflict_ids(value, diagnostics, record_id),
            )
        )
    return records, available


def _load_uel_mappings(
    path: Path,
    diagnostics: list[AcademicDataDiagnostic],
) -> tuple[list[RawUELMappingRecord], bool]:
    values, available = _read_optional_array(path, diagnostics)
    records: list[RawUELMappingRecord] = []
    for index, value in enumerate(values):
        record_id = f"uel-mapping[{index}]"
        if not isinstance(value, dict):
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.SCHEMA_INVALID,
                    record_id=record_id,
                    field="record",
                )
            )
            continue
        mapping_id = _required_string(
            value, "mapping_id", diagnostics, record_id=record_id
        )
        regulation = _required_integer(
            value, "regulation", diagnostics, record_id=record_id
        )
        uel_module_id = _required_string(
            value, "uel_module_id", diagnostics, record_id=record_id
        )
        asu_program = _required_string(
            value, "asu_program", diagnostics, record_id=record_id
        )
        asu_course_id = _required_string(
            value, "asu_course_id", diagnostics, record_id=record_id
        )
        mapping_type = _required_string(
            value, "mapping_type", diagnostics, record_id=record_id
        )
        weight_percent = _optional_number_field(
            value.get("weight_percent"),
            diagnostics,
            record_id=record_id,
            field="weight_percent",
        )
        source_id = _required_string(
            value, "source_id", diagnostics, record_id=record_id
        )
        approval_status = _required_string(
            value, "approval_status", diagnostics, record_id=record_id
        )
        if None in (
            mapping_id,
            regulation,
            uel_module_id,
            asu_program,
            asu_course_id,
            mapping_type,
            source_id,
            approval_status,
        ):
            continue
        records.append(
            RawUELMappingRecord(
                mapping_id=mapping_id,
                regulation=regulation,
                uel_module_id=uel_module_id,
                asu_program=asu_program,
                asu_course_id=asu_course_id,
                mapping_type=mapping_type,
                weight_percent=weight_percent,
                source_id=source_id,
                source_page=_source_page(value, diagnostics, record_id),
                verification_status=_optional_string(
                    value, "verification_status", diagnostics, record_id
                ),
                approval_status=approval_status,
                conflict_ids=_conflict_ids(value, diagnostics, record_id),
            )
        )
    return records, available


def _load_manifest(
    path: Path,
    diagnostics: list[AcademicDataDiagnostic],
) -> DatasetVersion | None:
    if not path.is_file():
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.MANIFEST_MISSING_OR_INVALID,
                planning_code=PlanningErrorCode.DATA_NOT_FOUND,
                field="dataset_version",
                detail=str(path),
                requires_human_review=True,
            )
        )
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.MANIFEST_MISSING_OR_INVALID,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                field="dataset_version",
                detail=str(path),
                requires_human_review=True,
            )
        )
        return None
    if not isinstance(value, dict) or not isinstance(value.get("dataset_version"), str):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.MANIFEST_MISSING_OR_INVALID,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                field="dataset_version",
                detail=str(path),
                requires_human_review=True,
            )
        )
        return None
    version = value["dataset_version"].strip()
    if not version:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.MANIFEST_MISSING_OR_INVALID,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                field="dataset_version",
                detail=str(path),
                requires_human_review=True,
            )
        )
        return None
    source_hash = value.get("source_hash")
    if source_hash is not None and not isinstance(source_hash, str):
        source_hash = None
    return DatasetVersion(
        version=version,
        source=str(path),
        revision=source_hash,
    )


def _parse_expression(
    value: object,
    diagnostics: list[AcademicDataDiagnostic],
    *,
    record_id: str,
) -> RawExpression | None:
    if not isinstance(value, dict):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.INCOMPLETE_EXPRESSION,
                planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
                record_id=record_id,
                field="expression",
                requires_human_review=True,
            )
        )
        return None
    source_type = value.get("type")
    if not isinstance(source_type, str) or not source_type.strip():
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.INCOMPLETE_EXPRESSION,
                planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
                record_id=record_id,
                field="expression.type",
                requires_human_review=True,
            )
        )
        return None
    children: list[RawExpression] = []
    raw_conditions = value.get("conditions")
    if raw_conditions is not None:
        if not isinstance(raw_conditions, list) or not raw_conditions:
            diagnostics.append(
                _diagnostic(
                    AcademicDataDiagnosticCode.INCOMPLETE_EXPRESSION,
                    planning_code=PlanningErrorCode.UNSUPPORTED_RULE,
                    record_id=record_id,
                    source_type=source_type,
                    field="expression.conditions",
                    requires_human_review=True,
                )
            )
            return None
        for child in raw_conditions:
            parsed = _parse_expression(child, diagnostics, record_id=record_id)
            if parsed is None:
                children.append(
                    RawExpression(
                        source_type="INCOMPLETE_EXPRESSION",
                        reason="child expression could not be parsed",
                    )
                )
            else:
                children.append(parsed)
    return RawExpression(
        source_type=source_type,
        conditions=tuple(children),
        course_id=_optional_string(value, "course_id", diagnostics, record_id),
        course_code=_optional_string(value, "course_code", diagnostics, record_id),
        code=_optional_string(value, "code", diagnostics, record_id),
        value=_optional_scalar(value, "value", diagnostics, record_id),
        condition_note=_optional_string(
            value, "condition_note", diagnostics, record_id
        ),
        reason=_optional_string(value, "reason", diagnostics, record_id),
        external_reference=_optional_bool(
            value, "external_reference", diagnostics, record_id
        ),
    )


def _read_array(
    path: Path,
    diagnostics: list[AcademicDataDiagnostic],
) -> list[object]:
    if not path.is_file():
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SOURCE_UNAVAILABLE,
                planning_code=PlanningErrorCode.DATA_NOT_FOUND,
                detail=str(path),
                requires_human_review=True,
            )
        )
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                detail=str(path),
                requires_human_review=True,
            )
        )
        return []
    if not isinstance(value, list):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                detail=str(path),
                field="root",
                requires_human_review=True,
            )
        )
        return []
    return value


def _read_optional_array(
    path: Path,
    diagnostics: list[AcademicDataDiagnostic],
) -> tuple[list[object], bool]:
    """Read an optional capability artifact without masking malformed files."""

    if not path.is_file():
        return [], False
    return _read_array(path, diagnostics), True


def _required_string(
    value: dict[str, Any],
    field: str,
    diagnostics: list[AcademicDataDiagnostic],
    *,
    record_id: str,
) -> str | None:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.MISSING_REQUIRED_FIELD,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=record_id,
                field=field,
                requires_human_review=True,
            )
        )
        return None
    return raw


def _optional_string(
    value: dict[str, Any],
    field: str,
    diagnostics: list[AcademicDataDiagnostic],
    record_id: str,
) -> str | None:
    raw = value.get(field)
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=record_id,
                field=field,
            )
        )
        return None
    return raw


def _required_integer(
    value: dict[str, Any],
    field: str,
    diagnostics: list[AcademicDataDiagnostic],
    *,
    record_id: str,
) -> int | None:
    raw = value.get(field)
    if isinstance(raw, bool) or not isinstance(raw, int):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.MISSING_REQUIRED_FIELD,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=record_id,
                field=field,
                requires_human_review=True,
            )
        )
        return None
    return raw


def _required_number(
    value: dict[str, Any],
    field: str,
    diagnostics: list[AcademicDataDiagnostic],
    *,
    record_id: str,
) -> int | float | None:
    raw = value.get(field)
    if (
        isinstance(raw, bool)
        or not isinstance(raw, (int, float))
        or not math.isfinite(raw)
    ):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.MISSING_REQUIRED_FIELD,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=record_id,
                field=field,
                requires_human_review=True,
            )
        )
        return None
    return raw


def _optional_bool(
    value: dict[str, Any],
    field: str,
    diagnostics: list[AcademicDataDiagnostic],
    record_id: str,
) -> bool | None:
    raw = value.get(field)
    if raw is None:
        return None
    if not isinstance(raw, bool):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=record_id,
                field=field,
            )
        )
        return None
    return raw


def _optional_scalar(
    value: dict[str, Any],
    field: str,
    diagnostics: list[AcademicDataDiagnostic],
    record_id: str,
) -> int | float | str | bool | None:
    raw = value.get(field)
    if raw is None or isinstance(raw, (str, bool)):
        return raw
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        if math.isfinite(raw):
            return raw
    diagnostics.append(
        _diagnostic(
            AcademicDataDiagnosticCode.SCHEMA_INVALID,
            planning_code=PlanningErrorCode.INVALID_REQUEST,
            record_id=record_id,
            field=field,
        )
    )
    return None


def _string_tuple(
    value: object,
    diagnostics: list[AcademicDataDiagnostic],
    *,
    record_id: str,
    field: str,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                record_id=record_id,
                field=field,
            )
        )
        return ()
    return tuple(dict.fromkeys(value))


def _optional_number_field(
    value: object,
    diagnostics: list[AcademicDataDiagnostic],
    *,
    record_id: str,
    field: str,
) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                record_id=record_id,
                field=field,
            )
        )
        return None
    if not math.isfinite(value):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                record_id=record_id,
                field=field,
            )
        )
        return None
    return value


def _optional_integer_field(
    value: object,
    diagnostics: list[AcademicDataDiagnostic],
    *,
    record_id: str,
    field: str,
) -> int | None:
    number = _optional_number_field(
        value,
        diagnostics,
        record_id=record_id,
        field=field,
    )
    if number is None:
        return None
    if isinstance(number, float) and not number.is_integer():
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                record_id=record_id,
                field=field,
            )
        )
        return None
    return int(number)


def _source_page(
    value: dict[str, Any],
    diagnostics: list[AcademicDataDiagnostic],
    record_id: str,
) -> int | str | None:
    raw = value.get("source_page")
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=record_id,
                field="source_page",
            )
        )
        return None
    if isinstance(raw, int) and raw < 1:
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=record_id,
                field="source_page",
            )
        )
        return None
    if isinstance(raw, str) and not raw.strip():
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=record_id,
                field="source_page",
            )
        )
        return None
    return raw


def _conflict_ids(
    value: dict[str, Any],
    diagnostics: list[AcademicDataDiagnostic],
    record_id: str,
) -> tuple[str, ...]:
    raw = value.get("conflict_ids", [])
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(
        isinstance(item, str) and item.strip() for item in raw
    ):
        diagnostics.append(
            _diagnostic(
                AcademicDataDiagnosticCode.SCHEMA_INVALID,
                planning_code=PlanningErrorCode.INVALID_REQUEST,
                record_id=record_id,
                field="conflict_ids",
            )
        )
        return ()
    return tuple(dict.fromkeys(raw))


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


def _has_source_unavailable(
    diagnostics: list[AcademicDataDiagnostic],
    path: Path,
) -> bool:
    return any(
        item.code is AcademicDataDiagnosticCode.SOURCE_UNAVAILABLE
        and item.detail == str(path)
        for item in diagnostics
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
            ),
        )
    )
