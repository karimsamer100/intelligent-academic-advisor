"""Typed contracts for the Academic Data Foundation adapter boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Generic, TypeVar

from ...domain.course import CourseIdentity
from ...domain.errors import PlanningErrorCode
from ...domain.provenance import Provenance
from ...domain.reasons import ReasonCode
from ...domain.version import DatasetVersion
from ...policy import ExecutionMode


class AcademicDataSourceMode(StrEnum):
    """Data tier selected by an adapter load."""

    NORMALIZED_DEVELOPMENT = "NORMALIZED_DEVELOPMENT"
    VERIFIED_AUTHORITATIVE = "VERIFIED_AUTHORITATIVE"


class AcademicDataDiagnosticCode(StrEnum):
    """Stable machine-readable adapter boundary diagnostics."""

    COURSE_NOT_FOUND = "COURSE_NOT_FOUND"
    DUPLICATE_RECORD = "DUPLICATE_RECORD"
    MALFORMED_IDENTITY = "MALFORMED_IDENTITY"
    UNSUPPORTED_ENTITY_KIND = "UNSUPPORTED_ENTITY_KIND"
    RULE_TARGET_MISMATCH = "RULE_TARGET_MISMATCH"
    DUPLICATE_RULE = "DUPLICATE_RULE"
    UNSUPPORTED_EXPRESSION = "UNSUPPORTED_EXPRESSION"
    INCOMPLETE_EXPRESSION = "INCOMPLETE_EXPRESSION"
    UNKNOWN_LIFECYCLE_VALUE = "UNKNOWN_LIFECYCLE_VALUE"
    CONFLICT_PRESENT = "CONFLICT_PRESENT"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    MANIFEST_MISSING_OR_INVALID = "MANIFEST_MISSING_OR_INVALID"
    DATASET_MODE_MISMATCH = "DATASET_MODE_MISMATCH"
    ELIGIBILITY_COVERAGE_GAP = "ELIGIBILITY_COVERAGE_GAP"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    UNKNOWN_SOURCE = "UNKNOWN_SOURCE"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    UNSUPPORTED_REQUIREMENT = "UNSUPPORTED_REQUIREMENT"


@dataclass(frozen=True, slots=True)
class AcademicDataConfig:
    """Filesystem and safety configuration for one adapter load."""

    package_root: Path
    source_mode: AcademicDataSourceMode
    manifest_path: Path | None = None
    requested_execution_mode: ExecutionMode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.package_root, Path):
            raise TypeError("package_root must be a pathlib.Path")
        if not isinstance(self.source_mode, AcademicDataSourceMode):
            raise TypeError("source_mode must be an AcademicDataSourceMode")
        if self.manifest_path is not None and not isinstance(self.manifest_path, Path):
            raise TypeError("manifest_path must be a pathlib.Path or None")
        if self.requested_execution_mode is not None and not isinstance(
            self.requested_execution_mode, ExecutionMode
        ):
            raise TypeError("requested_execution_mode must be an ExecutionMode or None")


@dataclass(frozen=True, slots=True)
class AcademicDataDiagnostic:
    """A structured data-quality or academic-coverage issue."""

    code: AcademicDataDiagnosticCode
    planning_code: PlanningErrorCode = PlanningErrorCode.INVALID_REQUEST
    reason_codes: tuple[ReasonCode, ...] = ()
    record_id: str | None = None
    course_id: CourseIdentity | None = None
    source_id: str | None = None
    source_type: str | None = None
    field: str | None = None
    conflict_ids: tuple[str, ...] = ()
    detail: str | None = None
    requires_human_review: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.code, AcademicDataDiagnosticCode):
            raise TypeError("code must be an AcademicDataDiagnosticCode")
        if not isinstance(self.planning_code, PlanningErrorCode):
            raise TypeError("planning_code must be a PlanningErrorCode")
        if not all(isinstance(reason, ReasonCode) for reason in self.reason_codes):
            raise TypeError("reason_codes must contain only ReasonCode values")
        if self.record_id is not None and (
            not isinstance(self.record_id, str) or not self.record_id.strip()
        ):
            raise ValueError("record_id must be non-empty when provided")
        if self.course_id is not None and not isinstance(
            self.course_id, CourseIdentity
        ):
            raise TypeError("course_id must be a CourseIdentity or None")
        for name in ("source_id", "source_type", "field", "detail"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be non-empty when provided")
        if not all(
            isinstance(conflict_id, str) and conflict_id.strip()
            for conflict_id in self.conflict_ids
        ):
            raise TypeError("conflict_ids must contain non-empty strings")
        if not isinstance(self.requires_human_review, bool):
            raise TypeError("requires_human_review must be a bool")
        object.__setattr__(
            self, "reason_codes", tuple(dict.fromkeys(self.reason_codes))
        )
        object.__setattr__(
            self,
            "conflict_ids",
            tuple(dict.fromkeys(self.conflict_ids)),
        )


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class AcademicDataLookup(Generic[T]):
    """Typed lookup value plus provenance and local adapter diagnostics."""

    value: T | None
    dataset_version: DatasetVersion | None
    provenance: tuple[Provenance, ...] = ()
    diagnostics: tuple[AcademicDataDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if self.dataset_version is not None and not isinstance(
            self.dataset_version, DatasetVersion
        ):
            raise TypeError("dataset_version must be a DatasetVersion or None")
        if not all(isinstance(item, Provenance) for item in self.provenance):
            raise TypeError("provenance must contain only Provenance values")
        if not all(
            isinstance(item, AcademicDataDiagnostic) for item in self.diagnostics
        ):
            raise TypeError(
                "diagnostics must contain only AcademicDataDiagnostic values"
            )
        object.__setattr__(self, "provenance", tuple(self.provenance))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True, slots=True)
class AcademicDataLoadResult(Generic[T]):
    """Result of loading one typed adapter snapshot."""

    value: T | None
    source_mode: AcademicDataSourceMode
    dataset_version: DatasetVersion | None
    diagnostics: tuple[AcademicDataDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source_mode, AcademicDataSourceMode):
            raise TypeError("source_mode must be an AcademicDataSourceMode")
        if self.dataset_version is not None and not isinstance(
            self.dataset_version, DatasetVersion
        ):
            raise TypeError("dataset_version must be a DatasetVersion or None")
        if not all(
            isinstance(item, AcademicDataDiagnostic) for item in self.diagnostics
        ):
            raise TypeError(
                "diagnostics must contain only AcademicDataDiagnostic values"
            )
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
