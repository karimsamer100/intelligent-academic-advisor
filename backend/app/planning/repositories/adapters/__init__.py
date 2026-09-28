"""Adapters from external academic-data representations into Planning types."""

from .academic_data_source import AcademicEligibilityDataSource
from .academic_data_types import (
    AcademicDataConfig,
    AcademicDataDiagnostic,
    AcademicDataDiagnosticCode,
    AcademicDataLoadResult,
    AcademicDataLookup,
    AcademicDataSourceMode,
)
from .academic_data_adapter import AcademicDataAdapter, JsonAcademicDataAdapter
from .student_json_repository import JsonStudentRepository, StudentRepositoryDataError

__all__ = [
    "AcademicDataAdapter",
    "AcademicDataConfig",
    "AcademicDataDiagnostic",
    "AcademicDataDiagnosticCode",
    "AcademicDataLoadResult",
    "AcademicDataLookup",
    "AcademicDataSourceMode",
    "AcademicEligibilityDataSource",
    "JsonAcademicDataAdapter",
    "JsonStudentRepository",
    "StudentRepositoryDataError",
]
