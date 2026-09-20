from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.planning.domain.course import (
    Course,
    CourseIdentity,
    Program,
    Regulation,
)
from app.planning.domain.dependency import (
    CycleKind,
    DependencyCoverageStatus,
    DependencyGraphDiagnosticCode,
    DependencyGraphScope,
    DependencyRelationKind,
)
from app.planning.domain.eligibility import (
    CourseEligibilityRuleSet,
    RuleSetStatus,
)
from app.planning.domain.expressions import (
    AndExpression,
    CourseConcurrentExpression,
    CoursePassedExpression,
    NotExpression,
    OrExpression,
    UnsupportedExpression,
)
from app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from app.planning.domain.rules import AcademicRule
from app.planning.graph.builder import DependencyGraphBuilder


def _identity(code: str, *, regulation: Regulation = Regulation.R18) -> CourseIdentity:
    program = Program("CESS" if regulation is Regulation.R18 else "CAIE")
    return CourseIdentity(regulation, program, code)


def _course(identity: CourseIdentity) -> Course:
    return Course(
        identity=identity,
        course_name=identity.course_code,
        credit_hours=3,
        approval_status=ApprovalStatus.APPROVED,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )


def _rule(
    target: CourseIdentity,
    expression: object,
    *,
    rule_id: str = "PR-001",
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
) -> AcademicRule:
    return AcademicRule(
        rule_id=rule_id,
        regulation=target.regulation,
        program=target.program,
        approval_status=approval_status,
        verification_status=VerificationStatus.SOURCE_VERIFIED,
        critical_for_planner=True,
        expression=expression,  # type: ignore[arg-type]
    )


def _rule_set(
    target: CourseIdentity,
    expression: object,
    *,
    status: RuleSetStatus = RuleSetStatus.COMPLETE,
    rule_id: str = "PR-001",
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
) -> CourseEligibilityRuleSet:
    return CourseEligibilityRuleSet(
        target_course=target,
        status=status,
        rules=(
            _rule(target, expression, rule_id=rule_id, approval_status=approval_status),
        ),
    )


def _build(
    courses: tuple[Course, ...],
    rule_sets: tuple[CourseEligibilityRuleSet, ...],
):
    scope = DependencyGraphScope(Regulation.R18, Program("CESS"))
    return DependencyGraphBuilder().build(
        scope=scope,
        courses=courses,
        rule_sets=rule_sets,
    )


def test_empty_graph_is_constructed_for_a_scope() -> None:
    result = _build((), ())

    assert result.graph.scope == DependencyGraphScope(Regulation.R18, Program("CESS"))
    assert result.graph.nodes == ()
    assert result.graph.references == ()
    assert result.diagnostics == ()


def test_direct_course_dependency_is_required_and_queryable() -> None:
    prerequisite = _identity("CSE111")
    target = _identity("CSE112")

    result = _build(
        (_course(prerequisite), _course(target)),
        (_rule_set(target, CoursePassedExpression(prerequisite)),),
    )

    dependencies = result.graph.direct_dependencies(target)
    assert len(dependencies) == 1
    assert dependencies[0].dependency == prerequisite
    assert dependencies[0].relation_kind is DependencyRelationKind.REQUIRED
    assert dependencies[0].traversable is True
    assert result.graph.direct_dependents(prerequisite)[0].target_course == target
    assert result.graph.has_path(prerequisite, target) is True
    assert result.graph.ancestors(target) == (prerequisite,)
    assert result.graph.descendants(prerequisite) == (target,)


def test_concurrent_reference_is_preserved_but_not_a_prior_pass_edge() -> None:
    prerequisite = _identity("CSE392")
    target = _identity("CSE493")

    result = _build(
        (_course(prerequisite), _course(target)),
        (_rule_set(target, CourseConcurrentExpression(prerequisite)),),
    )

    reference = result.graph.direct_dependencies(target)[0]
    assert reference.relation_kind is DependencyRelationKind.CONCURRENT
    assert reference.traversable is False
    assert result.graph.has_path(prerequisite, target) is False


def test_and_expression_preserves_constraint_and_two_required_references() -> None:
    first = _identity("CSE111")
    second = _identity("CSE131")
    target = _identity("CSE112")
    expression = AndExpression(
        (CoursePassedExpression(first), CoursePassedExpression(second))
    )

    result = _build(
        (_course(first), _course(second), _course(target)),
        (_rule_set(target, expression),),
    )

    definition = result.graph.definition_for(target)
    assert definition is not None
    assert definition.constraints[0].expression == expression
    assert definition.dependency_coverage is DependencyCoverageStatus.COMPLETE
    assert [item.dependency for item in result.graph.direct_dependencies(target)] == [
        first,
        second,
    ]
    assert all(
        item.relation_kind is DependencyRelationKind.REQUIRED
        for item in result.graph.direct_dependencies(target)
    )


def test_nested_and_or_preserves_tree_and_marks_only_definitely_required_reference() -> (
    None
):
    first = _identity("CSE111")
    second = _identity("CSE131")
    third = _identity("CSE141")
    target = _identity("CSE112")
    expression = AndExpression(
        (
            CoursePassedExpression(first),
            OrExpression(
                (CoursePassedExpression(second), CoursePassedExpression(third))
            ),
        )
    )

    result = _build(
        tuple(_course(identity) for identity in (first, second, third, target)),
        (_rule_set(target, expression),),
    )

    definition = result.graph.definition_for(target)
    assert definition is not None
    assert definition.constraints[0].expression == expression
    references = result.graph.direct_dependencies(target)
    assert [item.dependency for item in references] == [first, second, third]
    assert references[0].relation_kind is DependencyRelationKind.REQUIRED
    assert references[1].relation_kind is DependencyRelationKind.ALTERNATIVE
    assert references[2].relation_kind is DependencyRelationKind.ALTERNATIVE


def test_missing_rule_set_is_unavailable_and_does_not_become_complete_empty() -> None:
    target = _identity("CSE112")

    result = _build((_course(target),), ())

    definition = result.graph.definition_for(target)
    assert definition is not None
    assert definition.dependency_coverage is DependencyCoverageStatus.UNAVAILABLE
    assert definition.eligibility_rule_set_status is RuleSetStatus.UNAVAILABLE
    assert any(
        diagnostic.code is DependencyGraphDiagnosticCode.RULE_SET_UNAVAILABLE
        for diagnostic in result.diagnostics
    )


def test_incomplete_eligibility_status_does_not_poison_complete_direct_dependency_coverage() -> (
    None
):
    prerequisite = _identity("CSE111")
    target = _identity("CSE112")

    result = _build(
        (_course(prerequisite), _course(target)),
        (
            _rule_set(
                target,
                CoursePassedExpression(prerequisite),
                status=RuleSetStatus.INCOMPLETE,
            ),
        ),
    )

    definition = result.graph.definition_for(target)
    assert definition is not None
    assert definition.dependency_coverage is DependencyCoverageStatus.COMPLETE
    assert definition.eligibility_rule_set_status is RuleSetStatus.INCOMPLETE


def test_unknown_same_scope_reference_is_preserved_but_not_fabricated() -> None:
    prerequisite = _identity("CSE999")
    target = _identity("CSE112")

    result = _build(
        (_course(target),),
        (_rule_set(target, CoursePassedExpression(prerequisite)),),
    )

    reference = result.graph.direct_dependencies(target)[0]
    assert reference.dependency == prerequisite
    assert reference.node_present is False
    assert result.graph.has_node(prerequisite) is False
    assert any(
        diagnostic.code is DependencyGraphDiagnosticCode.UNKNOWN_NODE
        for diagnostic in result.diagnostics
    )


def test_cross_scope_reference_is_not_a_positive_graph_edge() -> None:
    target = _identity("CSE112")
    other_scope = CourseIdentity(Regulation.R23, Program("CAIE"), "CSE111")

    result = _build(
        (_course(target),),
        (_rule_set(target, CoursePassedExpression(other_scope)),),
    )

    reference = result.graph.direct_dependencies(target)[0]
    assert reference.dependency == other_scope
    assert reference.traversable is False
    assert reference.relation_kind is DependencyRelationKind.UNRESOLVED
    assert result.graph.has_path(other_scope, target) is False
    assert any(
        diagnostic.code is DependencyGraphDiagnosticCode.CROSS_SCOPE_REFERENCE
        for diagnostic in result.diagnostics
    )


def test_out_of_scope_course_input_is_reported_without_poisoning_the_graph() -> None:
    scope = DependencyGraphScope(Regulation.R18, Program("CESS"))
    course = _course(CourseIdentity(Regulation.R23, Program("CAIE"), "CSE111"))

    result = DependencyGraphBuilder().build(
        scope=scope, courses=(course,), rule_sets=()
    )

    assert result.graph.nodes == ()
    assert any(
        diagnostic.code is DependencyGraphDiagnosticCode.CROSS_SCOPE_REFERENCE
        for diagnostic in result.diagnostics
    )


def test_nested_or_intersection_finds_reference_required_in_every_branch() -> None:
    shared = _identity("CSE111")
    left = _identity("CSE131")
    right = _identity("CSE141")
    target = _identity("CSE112")
    expression = OrExpression(
        (
            AndExpression(
                (CoursePassedExpression(shared), CoursePassedExpression(left))
            ),
            AndExpression(
                (CoursePassedExpression(shared), CoursePassedExpression(right))
            ),
        )
    )

    result = _build(
        tuple(_course(identity) for identity in (shared, left, right, target)),
        (_rule_set(target, expression),),
    )

    references = result.graph.direct_dependencies(target)
    assert [item.dependency for item in references] == [shared, shared, left, right]
    assert [item.relation_kind for item in references if item.dependency == shared] == [
        DependencyRelationKind.REQUIRED,
        DependencyRelationKind.REQUIRED,
    ]
    assert all(
        item.relation_kind is DependencyRelationKind.ALTERNATIVE
        for item in references
        if item.dependency in {left, right}
    )


def test_or_with_unsupported_branch_does_not_infer_a_required_course() -> None:
    prerequisite = _identity("CSE111")
    target = _identity("CSE112")
    expression = OrExpression(
        (
            CoursePassedExpression(prerequisite),
            UnsupportedExpression(source_type="UNRESOLVED_CONDITION"),
        )
    )

    result = _build(
        (_course(prerequisite), _course(target)),
        (_rule_set(target, expression),),
    )

    reference = result.graph.direct_dependencies(target)[0]
    assert reference.relation_kind is DependencyRelationKind.ALTERNATIVE
    assert result.graph.definition_for(target).dependency_coverage is (  # type: ignore[union-attr]
        DependencyCoverageStatus.INCOMPLETE
    )


def test_and_with_unsupported_branch_keeps_supported_course_required() -> None:
    prerequisite = _identity("CSE111")
    target = _identity("CSE112")
    expression = AndExpression(
        (
            CoursePassedExpression(prerequisite),
            UnsupportedExpression(source_type="UNRESOLVED_CONDITION"),
        )
    )

    result = _build(
        (_course(prerequisite), _course(target)),
        (_rule_set(target, expression),),
    )

    reference = result.graph.direct_dependencies(target)[0]
    assert reference.relation_kind is DependencyRelationKind.REQUIRED
    assert result.graph.definition_for(target).dependency_coverage is (  # type: ignore[union-attr]
        DependencyCoverageStatus.INCOMPLETE
    )


def test_not_course_reference_is_preserved_without_positive_traversal() -> None:
    prerequisite = _identity("CSE111")
    target = _identity("CSE112")
    result = _build(
        (_course(prerequisite), _course(target)),
        (_rule_set(target, NotExpression(CoursePassedExpression(prerequisite))),),
    )

    reference = result.graph.direct_dependencies(target)[0]
    assert reference.relation_kind is DependencyRelationKind.UNRESOLVED
    assert reference.traversable is False
    assert result.graph.has_path(prerequisite, target) is False


def test_external_reference_is_typed_and_not_indexed_as_a_course_node() -> None:
    target = _identity("CSE112")
    result = _build(
        (_course(target),),
        (
            _rule_set(
                target,
                UnsupportedExpression(
                    source_type="CONDITIONAL_COURSE_PASSED",
                    course_code="ASU041",
                    external_reference=True,
                ),
            ),
        ),
    )

    external = result.graph.external_references(target)
    assert len(external) == 1
    assert external[0].dependency.reference == "ASU041"  # type: ignore[union-attr]
    assert result.graph.has_node(_identity("ASU041")) is False
    assert any(
        diagnostic.code is DependencyGraphDiagnosticCode.EXTERNAL_REFERENCE
        for diagnostic in result.diagnostics
    )


def test_blocked_rule_preserves_lifecycle_and_makes_dependency_coverage_incomplete() -> (
    None
):
    prerequisite = _identity("CSE111")
    target = _identity("CSE112")
    result = _build(
        (_course(prerequisite), _course(target)),
        (
            _rule_set(
                target,
                CoursePassedExpression(prerequisite),
                approval_status=ApprovalStatus.BLOCKED,
            ),
        ),
    )

    reference = result.graph.direct_dependencies(target)[0]
    assert reference.approval_status is ApprovalStatus.BLOCKED
    assert result.graph.definition_for(target).dependency_coverage is (  # type: ignore[union-attr]
        DependencyCoverageStatus.INCOMPLETE
    )


def test_exact_duplicate_nodes_are_reported_without_silent_normalization() -> None:
    target = _identity("CSE112")
    course = _course(target)
    result = _build((course, course), ())

    assert len(result.graph.nodes) == 1
    assert any(
        diagnostic.code is DependencyGraphDiagnosticCode.DUPLICATE_NODE
        for diagnostic in result.diagnostics
    )


def test_dependency_graph_contracts_are_immutable() -> None:
    target = _identity("CSE112")
    result = _build((_course(target),), ())

    with pytest.raises(FrozenInstanceError):
        result.graph.scope = DependencyGraphScope(Regulation.R18, Program("CESS"))


def test_input_order_does_not_change_graph_or_diagnostics() -> None:
    first = _identity("CSE111")
    second = _identity("CSE131")
    target = _identity("CSE112")
    rule_set = _rule_set(
        target,
        AndExpression((CoursePassedExpression(first), CoursePassedExpression(second))),
    )
    courses = (_course(first), _course(second), _course(target))

    forward = _build(courses, (rule_set,))
    reverse = _build(tuple(reversed(courses)), (rule_set,))

    assert forward.graph == reverse.graph
    assert forward.diagnostics == reverse.diagnostics


def test_self_dependency_is_reported_as_a_mandatory_cycle() -> None:
    course = _identity("CSE111")
    result = _build(
        (_course(course),),
        (_rule_set(course, CoursePassedExpression(course)),),
    )

    assert len(result.graph.cycles) == 1
    cycle = result.graph.cycles[0]
    assert cycle.kind is CycleKind.MANDATORY
    assert cycle.members == (course,)
    assert cycle.representative_path == (course, course)
    assert any(
        diagnostic.code is DependencyGraphDiagnosticCode.SELF_DEPENDENCY
        for diagnostic in result.diagnostics
    )


def test_two_node_required_cycle_is_one_deterministic_mandatory_scc() -> None:
    first = _identity("CSE111")
    second = _identity("CSE112")
    result = _build(
        (_course(first), _course(second)),
        (
            _rule_set(first, CoursePassedExpression(second), rule_id="PR-FIRST"),
            _rule_set(second, CoursePassedExpression(first), rule_id="PR-SECOND"),
        ),
    )

    assert len(result.graph.cycles) == 1
    cycle = result.graph.cycles[0]
    assert cycle.kind is CycleKind.MANDATORY
    assert cycle.members == (first, second)
    assert cycle.rule_ids == ("PR-FIRST", "PR-SECOND")
    assert cycle.representative_path == (first, second, first)


def test_or_only_cycle_is_reference_cycle_not_mandatory_cycle() -> None:
    first = _identity("CSE111")
    second = _identity("CSE112")
    alternative = _identity("CSE131")
    result = _build(
        (_course(first), _course(second), _course(alternative)),
        (
            _rule_set(
                first,
                OrExpression(
                    (
                        CoursePassedExpression(second),
                        CoursePassedExpression(alternative),
                    )
                ),
                rule_id="PR-FIRST",
            ),
            _rule_set(
                second,
                CoursePassedExpression(first),
                rule_id="PR-SECOND",
            ),
        ),
    )

    assert len(result.graph.cycles) == 1
    cycle = result.graph.cycles[0]
    assert cycle.kind is CycleKind.REFERENCE
    assert cycle.members == (first, second)
    assert cycle.rule_ids == ("PR-FIRST", "PR-SECOND")
    assert all(item.kind is not CycleKind.MANDATORY for item in result.graph.cycles)


def test_longer_scc_and_cycle_diagnostics_are_input_order_independent() -> None:
    first = _identity("CSE111")
    second = _identity("CSE112")
    third = _identity("CSE131")
    courses = (_course(first), _course(second), _course(third))
    rule_sets = (
        _rule_set(first, CoursePassedExpression(second), rule_id="PR-FIRST"),
        _rule_set(second, CoursePassedExpression(third), rule_id="PR-SECOND"),
        _rule_set(third, CoursePassedExpression(first), rule_id="PR-THIRD"),
    )

    forward = _build(courses, rule_sets)
    reverse = _build(tuple(reversed(courses)), tuple(reversed(rule_sets)))

    assert forward.graph.cycles == reverse.graph.cycles
    assert forward.diagnostics == reverse.diagnostics
    assert forward.graph.cycles[0].members == (first, second, third)


def test_multiple_cycle_components_have_deterministic_order() -> None:
    first = _identity("CSE111")
    second = _identity("CSE112")
    third = _identity("CSE131")
    fourth = _identity("CSE141")
    courses = tuple(_course(identity) for identity in (first, second, third, fourth))
    rule_sets = (
        _rule_set(first, CoursePassedExpression(second), rule_id="PR-FIRST"),
        _rule_set(second, CoursePassedExpression(first), rule_id="PR-SECOND"),
        _rule_set(third, CoursePassedExpression(fourth), rule_id="PR-THIRD"),
        _rule_set(fourth, CoursePassedExpression(third), rule_id="PR-FOURTH"),
    )

    result = _build(tuple(reversed(courses)), tuple(reversed(rule_sets)))

    assert [cycle.members for cycle in result.graph.cycles] == [
        (first, second),
        (third, fourth),
    ]


def test_unknown_query_identity_has_total_empty_query_behavior() -> None:
    target = _identity("CSE112")
    dependency = _identity("CSE111")
    unknown = _identity("CSE999")
    result = _build(
        (_course(target),),
        (_rule_set(target, CoursePassedExpression(dependency)),),
    )

    assert result.graph.has_node(unknown) is False
    assert result.graph.direct_dependencies(unknown) == ()
    assert result.graph.external_references(unknown) == ()
    assert result.graph.direct_dependents(unknown) == ()


def test_cycle_detection_does_not_fabricate_missing_nodes() -> None:
    present = _identity("CSE111")
    missing = _identity("CSE112")
    result = _build(
        (_course(present),),
        (
            _rule_set(present, CoursePassedExpression(missing), rule_id="PR-PRESENT"),
            _rule_set(missing, CoursePassedExpression(present), rule_id="PR-MISSING"),
        ),
    )

    assert result.graph.has_node(missing) is False
    assert result.graph.cycles == ()
