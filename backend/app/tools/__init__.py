"""Application tools exposed to future LLM orchestration."""

from app.tools.context import ToolExecutionContext
from app.tools.degree_audit import DegreeAuditArguments, DegreeAuditTool
from app.tools.eligibility import (
    CheckCourseEligibilityArguments,
    CheckCourseEligibilityTool,
)
from app.tools.errors import (
    ToolArgumentValidationError,
    ToolContextRequiredError,
    ToolDataUnavailableError,
    ToolDuplicateNameError,
    ToolError,
    ToolExecutionError,
    ToolCompositionError,
    UnknownToolError,
)
from app.tools.factory import build_academic_tool_registry
from app.tools.interface import AcademicTool
from app.tools.rag import SearchOfficialDocumentsArguments, SearchOfficialDocumentsTool
from app.tools.registry import ToolRegistry

__all__ = [
    "AcademicTool",
    "build_academic_tool_registry",
    "CheckCourseEligibilityArguments",
    "CheckCourseEligibilityTool",
    "DegreeAuditArguments",
    "DegreeAuditTool",
    "SearchOfficialDocumentsArguments",
    "SearchOfficialDocumentsTool",
    "ToolArgumentValidationError",
    "ToolContextRequiredError",
    "ToolDataUnavailableError",
    "ToolDuplicateNameError",
    "ToolError",
    "ToolCompositionError",
    "ToolExecutionContext",
    "ToolExecutionError",
    "ToolRegistry",
    "UnknownToolError",
]
