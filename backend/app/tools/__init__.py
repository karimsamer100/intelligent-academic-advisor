"""Application tools exposed to future LLM orchestration."""

from app.tools.context import ToolExecutionContext
from app.tools.eligibility import (
    CheckCourseEligibilityArguments,
    CheckCourseEligibilityTool,
)
from app.tools.errors import (
    ToolArgumentValidationError,
    ToolContextRequiredError,
    ToolDataUnavailableError,
    ToolError,
    ToolExecutionError,
)
from app.tools.interface import AcademicTool
from app.tools.rag import SearchOfficialDocumentsArguments, SearchOfficialDocumentsTool

__all__ = [
    "AcademicTool",
    "CheckCourseEligibilityArguments",
    "CheckCourseEligibilityTool",
    "SearchOfficialDocumentsArguments",
    "SearchOfficialDocumentsTool",
    "ToolArgumentValidationError",
    "ToolContextRequiredError",
    "ToolDataUnavailableError",
    "ToolError",
    "ToolExecutionContext",
    "ToolExecutionError",
]
