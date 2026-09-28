"""Safe errors raised at the application-tool boundary."""


class ToolError(Exception):
    """Base class for expected tool-boundary failures."""


class ToolArgumentValidationError(ToolError):
    """The LLM supplied missing, invalid, or unknown tool arguments."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Invalid arguments for tool '{tool_name}'")


class ToolContextRequiredError(ToolError):
    """A tool requires trusted server-owned student context."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Tool '{tool_name}' requires trusted student context")


class ToolDataUnavailableError(ToolError):
    """Trusted student or academic source data cannot support the tool call."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Required trusted data is unavailable for tool '{tool_name}'")


class ToolExecutionError(ToolError):
    """A tool could not produce a JSON-serializable result."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Tool '{tool_name}' failed to produce a valid result")


class ToolDuplicateNameError(ToolError):
    """A registry already contains the requested stable tool name."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Tool name '{tool_name}' is already registered")


class UnknownToolError(ToolError):
    """The requested tool name is not registered."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Unknown tool '{tool_name}'")


class ToolCompositionError(ToolError):
    """Required application dependencies cannot safely compose the tools."""

    def __init__(self) -> None:
        super().__init__("Academic tools could not be composed from configured data")


__all__ = [
    "ToolArgumentValidationError",
    "ToolContextRequiredError",
    "ToolDataUnavailableError",
    "ToolDuplicateNameError",
    "ToolError",
    "ToolExecutionError",
    "ToolCompositionError",
    "UnknownToolError",
]
