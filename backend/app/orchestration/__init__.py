"""Application orchestration between the LLM and approved academic tools."""

from app.orchestration.composition import (
    AdvisorApplication,
    AdvisorStaticDependencies,
    build_advisor_application,
    build_advisor_static_dependencies,
)
from app.orchestration.contracts import AdvisorRequest, AdvisorResponse
from app.orchestration.orchestrator import AdvisorOrchestrator

__all__ = [
    "AdvisorApplication",
    "AdvisorOrchestrator",
    "AdvisorRequest",
    "AdvisorResponse",
    "AdvisorStaticDependencies",
    "build_advisor_application",
    "build_advisor_static_dependencies",
]
