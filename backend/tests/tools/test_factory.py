from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.rag_service import RAGService
from app.tools.context import ToolExecutionContext
from app.tools.degree_audit import DegreeAuditTool
from app.tools.errors import ToolCompositionError
from app.tools.eligibility import CheckCourseEligibilityTool
from app.tools.factory import build_academic_tool_registry
from app.tools.rag import SearchOfficialDocumentsTool


@pytest.fixture(scope="session")
def academic_data_root() -> Path:
    docker_root = Path("/data/academic")
    repository_root = Path(__file__).resolve().parents[3]
    local_root = repository_root / "data" / "academic"
    for candidate in (docker_root, local_root):
        if candidate.is_dir():
            return candidate.resolve()
    raise pytest.UsageError("Academic data package not found for tool composition tests")


def _academic_package(
    tmp_path: Path,
    academic_data_root: Path,
    *,
    include_manifest: bool = True,
) -> Path:
    package_root = tmp_path / "academic"
    shutil.copytree(academic_data_root / "normalized", package_root / "normalized")
    if include_manifest:
        (package_root / "normalized" / "dataset_manifest.json").write_text(
            json.dumps({"dataset_version": "tool-factory-test"}),
            encoding="utf-8",
        )
    return package_root


def _student_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "students" / "students.json"


def _settings(academic_path: Path | None) -> Settings:
    return Settings(
        academic_data_foundation_path=academic_path,
        student_data_path=_student_path(),
    )


def test_factory_composes_exactly_the_initial_three_tools(
    tmp_path: Path,
    academic_data_root: Path,
) -> None:
    settings = _settings(_academic_package(tmp_path, academic_data_root))

    registry = build_academic_tool_registry(RAGService(), settings=settings)

    assert [definition.name for definition in registry.definitions] == [
        "check_course_eligibility",
        "degree_audit",
        "search_official_documents",
    ]
    assert isinstance(registry.get("check_course_eligibility"), CheckCourseEligibilityTool)
    assert isinstance(registry.get("degree_audit"), DegreeAuditTool)
    assert isinstance(registry.get("search_official_documents"), SearchOfficialDocumentsTool)


def test_factory_uses_configured_student_and_academic_sources(
    tmp_path: Path,
    academic_data_root: Path,
) -> None:
    settings = _settings(_academic_package(tmp_path, academic_data_root))
    registry = build_academic_tool_registry(RAGService(), settings=settings)

    result = registry.execute(
        "degree_audit",
        {},
        ToolExecutionContext(student_id="DEV-STUDENT-001"),
    )

    assert result["metadata"]["dataset_version"]["version"] == "tool-factory-test"
    assert result["requirement_set_status"] == "INCOMPLETE"
    assert result["requires_human_review"] is True


def test_factory_fails_safely_without_academic_foundation_path() -> None:
    with pytest.raises(ToolCompositionError):
        build_academic_tool_registry(RAGService(), settings=_settings(None))


def test_factory_fails_safely_when_adapter_has_no_dataset_version(
    tmp_path: Path,
    academic_data_root: Path,
) -> None:
    settings = _settings(
        _academic_package(tmp_path, academic_data_root, include_manifest=False)
    )

    with pytest.raises(ToolCompositionError):
        build_academic_tool_registry(RAGService(), settings=settings)
