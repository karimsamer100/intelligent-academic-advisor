from __future__ import annotations

import inspect

import app.tools.factory as factory_module
from app.tools.degree_audit import DegreeAuditTool
from app.tools.eligibility import CheckCourseEligibilityTool
from app.tools.factory import build_academic_tool_registry
from app.tools.rag import SearchOfficialDocumentsTool


class FakePlanningService:
    pass


class FakeRAGService:
    def search(self, request):
        raise AssertionError("factory test must not execute RAG")


class FakeStudentRepository:
    pass


class FakeAcademicData:
    pass


def _registry_with_dependencies():
    planning_service = FakePlanningService()
    rag_service = FakeRAGService()
    student_repository = FakeStudentRepository()
    academic_data = FakeAcademicData()
    registry = build_academic_tool_registry(
        planning_service=planning_service,
        rag_service=rag_service,
        student_repository=student_repository,
        academic_data=academic_data,
    )
    return registry, planning_service, rag_service, student_repository, academic_data


def test_factory_accepts_and_preserves_application_dependencies() -> None:
    registry, planning, rag, students, academic = _registry_with_dependencies()

    eligibility = registry.get("check_course_eligibility")
    audit = registry.get("degree_audit")
    documents = registry.get("search_official_documents")

    assert isinstance(eligibility, CheckCourseEligibilityTool)
    assert isinstance(audit, DegreeAuditTool)
    assert isinstance(documents, SearchOfficialDocumentsTool)
    assert eligibility._planning_service is planning
    assert eligibility._student_repository is students
    assert eligibility._academic_data is academic
    assert audit._planning_service is planning
    assert audit._student_repository is students
    assert audit._academic_data is academic
    assert documents._student_repository is students
    assert documents._rag_service is rag


def test_factory_creates_exactly_the_frozen_three_tool_set() -> None:
    registry, *_ = _registry_with_dependencies()

    assert [definition.name for definition in registry.definitions] == [
        "check_course_eligibility",
        "degree_audit",
        "search_official_documents",
    ]
    assert set(registry._tools) == {
        "check_course_eligibility",
        "degree_audit",
        "search_official_documents",
    }
    assert set(
        registry.get("check_course_eligibility").definition.input_schema[
            "properties"
        ]
    ) == {"course_code"}
    assert registry.get("degree_audit").definition.input_schema.get(
        "properties", {}
    ) == {}
    assert set(
        registry.get("search_official_documents").definition.input_schema[
            "properties"
        ]
    ) == {"query", "document_types"}


def test_factory_does_not_construct_planning_or_discover_data() -> None:
    source = inspect.getsource(factory_module)

    for forbidden in (
        "PlanningEngine",
        "EligibilityService",
        "DegreeAuditService",
        "ExecutionPolicy",
        "RuleEvaluator",
        "JsonAcademicDataAdapter",
        "get_settings",
        "academic_data_foundation_path",
    ):
        assert forbidden not in source
