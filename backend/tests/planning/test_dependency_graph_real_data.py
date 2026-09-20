from __future__ import annotations

from pathlib import Path

from app.planning.domain.course import CourseIdentity, Program, Regulation
from app.planning.domain.dependency import (
    DependencyCoverageStatus,
    DependencyGraphDiagnosticCode,
    DependencyGraphScope,
    DependencyRelationKind,
)
from app.planning.domain.eligibility import RuleSetStatus
from app.planning.domain.expressions import AndExpression, UnsupportedExpression
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.graph.builder import DependencyGraphBuilder
from app.planning.repositories.adapters.academic_data_adapter import (
    JsonAcademicDataAdapter,
)
from app.planning.repositories.adapters.academic_data_source import (
    AcademicEligibilityDataSource,
)
from app.planning.repositories.adapters.academic_data_types import (
    AcademicDataConfig,
    AcademicDataSourceMode,
)


def _adapter(academic_data_root: Path) -> JsonAcademicDataAdapter:
    loaded = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=academic_data_root,
            source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
        )
    )
    assert loaded.value is not None
    return loaded.value


def _identity(value: str) -> CourseIdentity:
    return CourseIdentity.parse(value)


def _build_for(adapter: JsonAcademicDataAdapter, *course_ids: str):
    identities = tuple(_identity(course_id) for course_id in course_ids)
    courses = tuple(adapter.get_course(identity).value for identity in identities)
    rule_sets = tuple(
        adapter.get_eligibility_rules(identity).value for identity in identities
    )
    assert all(course is not None for course in courses)
    assert all(rule_set is not None for rule_set in rule_sets)
    scope = DependencyGraphScope(identities[0].regulation, identities[0].program)
    return DependencyGraphBuilder().build(
        scope=scope,
        courses=tuple(course for course in courses if course is not None),
        rule_sets=tuple(rule_set for rule_set in rule_sets if rule_set is not None),
    )


def test_adapter_lists_only_typed_courses_in_deterministic_scope_order(
    academic_data_root: Path,
) -> None:
    adapter = _adapter(academic_data_root)

    courses = adapter.list_courses(
        regulation=Regulation.R18,
        program=Program("CESS"),
    )

    identities = tuple(course.identity.course_id for course in courses)
    assert identities == tuple(sorted(identities))
    assert all(":SLOT:" not in identity for identity in identities)
    assert all(identity.startswith("R18:CESS:") for identity in identities)


def test_real_cse112_has_complete_direct_dependency_coverage_but_incomplete_eligibility_coverage(
    academic_data_root: Path,
) -> None:
    result = _build_for(
        _adapter(academic_data_root),
        "R18:CESS:CSE111",
        "R18:CESS:CSE131",
        "R18:CESS:CSE112",
    )
    target = _identity("R18:CESS:CSE112")

    definition = result.graph.definition_for(target)
    assert definition is not None
    assert definition.dependency_coverage is DependencyCoverageStatus.COMPLETE
    assert definition.eligibility_rule_set_status is RuleSetStatus.INCOMPLETE
    references = result.graph.direct_dependencies(target)
    assert [reference.dependency for reference in references] == [
        _identity("R18:CESS:CSE111"),
        _identity("R18:CESS:CSE131"),
    ]
    assert all(
        reference.relation_kind is DependencyRelationKind.REQUIRED
        for reference in references
    )
    assert all(
        reference.provenance is not None
        and reference.provenance.rule_id == "PRE-R18:CESS:CSE112"
        and reference.provenance.source_id == "SRC-CESS_NEW_BYLAW_2018_PDF"
        and reference.provenance.source_page == 9
        for reference in references
    )


def test_real_multi_hop_chain_is_reachable_in_both_directions(
    academic_data_root: Path,
) -> None:
    result = _build_for(
        _adapter(academic_data_root),
        "R18:CESS:CSE131",
        "R18:CESS:CSE334",
        "R18:CESS:CSE232",
        "R18:CESS:CSE233",
    )
    first = _identity("R18:CESS:CSE131")
    last = _identity("R18:CESS:CSE233")

    assert result.graph.has_path(first, last) is True
    assert result.graph.has_path(last, first) is False
    assert result.graph.ancestors(last) == (
        _identity("R18:CESS:CSE131"),
        _identity("R18:CESS:CSE232"),
        _identity("R18:CESS:CSE334"),
    )
    assert result.graph.descendants(first) == (
        _identity("R18:CESS:CSE232"),
        _identity("R18:CESS:CSE233"),
        _identity("R18:CESS:CSE334"),
    )


def test_real_cse486_preserves_known_dependency_and_unresolved_child(
    academic_data_root: Path,
) -> None:
    result = _build_for(
        _adapter(academic_data_root),
        "R23:CAIE:PHM113",
        "R23:CAIE:CSE486",
    )
    target = _identity("R23:CAIE:CSE486")
    definition = result.graph.definition_for(target)
    assert definition is not None
    assert definition.dependency_coverage is DependencyCoverageStatus.INCOMPLETE
    assert definition.eligibility_rule_set_status is RuleSetStatus.INCOMPLETE
    assert result.graph.direct_dependencies(target)[0].dependency == _identity(
        "R23:CAIE:PHM113"
    )
    assert (
        result.graph.direct_dependencies(target)[0].approval_status
        is ApprovalStatus.BLOCKED
    )
    assert (
        result.graph.direct_dependencies(target)[0].verification_status
        is VerificationStatus.NEEDS_VERIFICATION
    )
    expression = definition.constraints[0].expression
    assert isinstance(expression, AndExpression)
    assert isinstance(expression.children[1], UnsupportedExpression)
    assert any(
        diagnostic.code
        is DependencyGraphDiagnosticCode.UNSUPPORTED_DEPENDENCY_EXPRESSION
        for diagnostic in result.diagnostics
    )


def test_real_conditional_prerequisites_remain_external_not_course_edges(
    academic_data_root: Path,
) -> None:
    result = _build_for(_adapter(academic_data_root), "R23:CAIE:PHM111")
    target = _identity("R23:CAIE:PHM111")
    definition = result.graph.definition_for(target)

    assert definition is not None
    assert definition.dependency_coverage is DependencyCoverageStatus.INCOMPLETE
    assert result.graph.direct_dependencies(target) == ()
    assert {
        reference.dependency.reference  # type: ignore[union-attr]
        for reference in result.graph.external_references(target)
    } == {"ASU041", "PHM011"}
    assert any(
        diagnostic.code is DependencyGraphDiagnosticCode.EXTERNAL_REFERENCE
        for diagnostic in result.diagnostics
    )


def test_real_entry_requirement_does_not_create_a_course_dependency(
    academic_data_root: Path,
) -> None:
    result = _build_for(_adapter(academic_data_root), "R18:CESS:MDP081")
    target = _identity("R18:CESS:MDP081")

    assert result.graph.direct_dependencies(target) == ()
    external = result.graph.external_references(target)[0].dependency
    assert external.reference == "Eng"  # type: ignore[union-attr]
    assert not isinstance(external, CourseIdentity)


def test_adapter_implements_the_extended_typed_source_boundary(
    academic_data_root: Path,
) -> None:
    assert isinstance(_adapter(academic_data_root), AcademicEligibilityDataSource)
