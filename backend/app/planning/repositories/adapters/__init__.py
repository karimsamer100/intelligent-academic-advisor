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
]
