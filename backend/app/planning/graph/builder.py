"""Build immutable dependency graphs from typed academic rule data."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from ..domain.course import Course, CourseIdentity
from ..domain.dependency import (
    CycleKind,
    DependencyConstraint,
    DependencyCoverageStatus,
    DependencyDiagnosticKind,
    DependencyDefinition,
    DependencyGraph,
    DependencyGraphBuildResult,
    DependencyGraphDiagnostic,
    DependencyGraphDiagnosticCode,
    DependencyGraphScope,
    DependencyNode,
    DependencyReference,
    DependencyRelationKind,
    DependencyCycle,
    ExternalDependencyReference,
)
from ..domain.eligibility import CourseEligibilityRuleSet, RuleSetStatus
from ..domain.expressions import (
    AndExpression,
    CourseCompletedExpression,
    CourseCurrentlyRegisteredExpression,
    CoursePassedExpression,
    NotExpression,
    OrExpression,
    RuleExpression,
    UnsupportedExpression,
)
from ..domain.lifecycle import ApprovalStatus
from ..domain.reasons import ReasonCode
from ..domain.rules import AcademicRule
from ..domain.provenance import Provenance
from ..domain.version import DatasetVersion


@dataclass(frozen=True, slots=True)
class _ReferenceOccurrence:
    course: CourseIdentity | None
    external: ExternalDependencyReference | None
    path: tuple[int, ...]
    positive: bool


@dataclass(frozen=True, slots=True)
class _ExpressionAnalysis:
    all_positive_references: frozenset[CourseIdentity]
    definitely_required_references: frozenset[CourseIdentity]
    occurrences: tuple[_ReferenceOccurrence, ...]
    contains_unsupported: bool = False


@dataclass(frozen=True, slots=True)
class DependencyGraphBuilder:
    """Pure builder over already-mapped courses and rule sets."""

    def build(
        self,
        *,
        scope: DependencyGraphScope,
        courses: Iterable[Course],
        rule_sets: Iterable[CourseEligibilityRuleSet],
        dataset_version: DatasetVersion | None = None,
    ) -> DependencyGraphBuildResult:
        if not isinstance(scope, DependencyGraphScope):
            raise TypeError("scope must be a DependencyGraphScope")
        if dataset_version is not None and not isinstance(
            dataset_version, DatasetVersion
        ):
            raise TypeError("dataset_version must be a DatasetVersion or None")

        course_values = tuple(courses)
        rule_set_values = tuple(rule_sets)
        if not all(isinstance(course, Course) for course in course_values):
            raise TypeError("courses must contain only Course values")
        if not all(
            isinstance(rule_set, CourseEligibilityRuleSet)
            for rule_set in rule_set_values
        ):
            raise TypeError(
                "rule_sets must contain only CourseEligibilityRuleSet values"
            )

        diagnostics: list[DependencyGraphDiagnostic] = []
        course_map: dict[CourseIdentity, Course] = {}
        invalid_course_ids: set[CourseIdentity] = set()
        for course in sorted(course_values, key=lambda item: item.identity.course_id):
            identity = course.identity
            if not scope.contains(identity):
                diagnostics.append(
                    _diagnostic(
                        DependencyGraphDiagnosticCode.CROSS_SCOPE_REFERENCE,
                        kind=DependencyDiagnosticKind.STRUCTURAL,
                        target_course=identity,
                        reason_codes=_scope_reasons(scope, identity),
                        detail="course is outside the requested graph scope",
                    )
                )
                continue
            if identity in invalid_course_ids:
                continue
            if identity in course_map:
                diagnostics.append(
                    _diagnostic(
                        DependencyGraphDiagnosticCode.DUPLICATE_NODE,
                        kind=DependencyDiagnosticKind.STRUCTURAL,
                        target_course=identity,
                        detail="duplicate course identity supplied",
                    )
                )
                if course_map[identity] != course:
                    invalid_course_ids.add(identity)
                    course_map.pop(identity, None)
                continue
            course_map[identity] = course

        rule_set_map: dict[CourseIdentity, CourseEligibilityRuleSet] = {}
        invalid_rule_set_targets: set[CourseIdentity] = set()
        for rule_set in sorted(
            rule_set_values, key=lambda item: item.target_course.course_id
        ):
            target = rule_set.target_course
            if not scope.contains(target):
                diagnostics.append(
                    _diagnostic(
                        DependencyGraphDiagnosticCode.CROSS_SCOPE_REFERENCE,
                        kind=DependencyDiagnosticKind.STRUCTURAL,
                        target_course=target,
                        reason_codes=_scope_reasons(scope, target),
                        detail="rule set is outside the requested graph scope",
                    )
                )
                continue
            if target in invalid_rule_set_targets:
                continue
            if target in rule_set_map:
                diagnostics.append(
                    _diagnostic(
                        DependencyGraphDiagnosticCode.DUPLICATE_RELATION,
                        kind=DependencyDiagnosticKind.STRUCTURAL,
                        target_course=target,
                        detail="duplicate target rule set supplied",
                    )
                )
                if rule_set_map[target] != rule_set:
                    invalid_rule_set_targets.add(target)
                    rule_set_map.pop(target, None)
                continue
            rule_set_map[target] = rule_set

        target_ids = set(course_map) | set(rule_set_map) | invalid_rule_set_targets
        definitions: list[DependencyDefinition] = []
        references: list[DependencyReference] = []

        for target in sorted(target_ids, key=lambda item: item.course_id):
            if target in invalid_rule_set_targets:
                definitions.append(
                    _definition(
                        target,
                        DependencyCoverageStatus.INCOMPLETE,
                        RuleSetStatus.INCOMPLETE,
                        (),
                        (ReasonCode.MISSING_REQUIRED_DATA,),
                    )
                )
                continue

            rule_set = rule_set_map.get(target)
            if rule_set is None:
                diagnostics.append(
                    _diagnostic(
                        DependencyGraphDiagnosticCode.RULE_SET_UNAVAILABLE,
                        kind=DependencyDiagnosticKind.SOURCE_COVERAGE,
                        target_course=target,
                        reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                        detail="no target rule set was supplied",
                    )
                )
                definitions.append(
                    _definition(
                        target,
                        DependencyCoverageStatus.UNAVAILABLE,
                        RuleSetStatus.UNAVAILABLE,
                        (),
                        (ReasonCode.MISSING_REQUIRED_DATA,),
                    )
                )
                continue

            constraints: list[DependencyConstraint] = []
            target_reasons = list(rule_set.reason_codes)
            direct_dependency_gap = rule_set.status is RuleSetStatus.UNAVAILABLE
            if not rule_set.rules and rule_set.status is not RuleSetStatus.COMPLETE:
                direct_dependency_gap = True

            for rule in rule_set.rules:
                constraint = _constraint(target, rule)
                constraints.append(constraint)
                rule_scope_valid = (
                    rule.regulation is target.regulation
                    and rule.program == target.program
                )
                if not rule_scope_valid:
                    direct_dependency_gap = True
                    diagnostics.append(
                        _diagnostic(
                            DependencyGraphDiagnosticCode.RULE_TARGET_MISMATCH,
                            kind=DependencyDiagnosticKind.STRUCTURAL,
                            target_course=target,
                            rule_id=rule.rule_id,
                            provenance=rule.provenance,
                            reason_codes=_rule_scope_reasons(target, rule),
                            detail="rule scope does not match its target course",
                        )
                    )

                if rule.expression is None:
                    direct_dependency_gap = True
                    target_reasons.append(ReasonCode.MISSING_REQUIRED_DATA)
                    diagnostics.append(
                        _diagnostic(
                            DependencyGraphDiagnosticCode.INCOMPLETE_DEPENDENCY_DATA,
                            kind=DependencyDiagnosticKind.SOURCE_COVERAGE,
                            target_course=target,
                            rule_id=rule.rule_id,
                            provenance=rule.provenance,
                            reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                            detail="rule has no executable expression",
                        )
                    )
                    continue

                analysis = _analyze_expression(rule.expression)
                if analysis.contains_unsupported:
                    direct_dependency_gap = True
                    target_reasons.append(ReasonCode.UNSUPPORTED_RULE)
                    diagnostics.append(
                        _diagnostic(
                            DependencyGraphDiagnosticCode.UNSUPPORTED_DEPENDENCY_EXPRESSION,
                            kind=DependencyDiagnosticKind.SOURCE_COVERAGE,
                            target_course=target,
                            rule_id=rule.rule_id,
                            provenance=rule.provenance,
                            reason_codes=(ReasonCode.UNSUPPORTED_RULE,),
                            detail="unsupported expression nodes were preserved",
                        )
                    )

                if rule.approval_status in {
                    ApprovalStatus.BLOCKED,
                    ApprovalStatus.CONFLICTED,
                    ApprovalStatus.SUPERSEDED,
                }:
                    direct_dependency_gap = True
                    target_reasons.append(
                        ReasonCode.CONFLICTED_RULE
                        if rule.approval_status is ApprovalStatus.CONFLICTED
                        else ReasonCode.BLOCKED_RULE
                        if rule.approval_status is ApprovalStatus.BLOCKED
                        else ReasonCode.UNAPPROVED_RULE
                    )

                for occurrence in analysis.occurrences:
                    reference = _reference_from_occurrence(
                        target=target,
                        rule=rule,
                        occurrence=occurrence,
                        required_courses=analysis.definitely_required_references,
                        course_map=course_map,
                        invalid_course_ids=invalid_course_ids,
                        rule_scope_valid=rule_scope_valid,
                    )
                    references.append(reference)
                    _append_reference_diagnostics(
                        diagnostics,
                        reference,
                        target=target,
                        rule=rule,
                    )

            if rule_set.status is RuleSetStatus.UNAVAILABLE:
                coverage = DependencyCoverageStatus.UNAVAILABLE
            elif direct_dependency_gap:
                coverage = DependencyCoverageStatus.INCOMPLETE
            else:
                coverage = DependencyCoverageStatus.COMPLETE
            definitions.append(
                _definition(
                    target,
                    coverage,
                    rule_set.status,
                    tuple(constraints),
                    tuple(target_reasons),
                )
            )

        nodes = tuple(
            DependencyNode(course)
            for _, course in sorted(
                course_map.items(), key=lambda item: item[0].course_id
            )
        )
        initial_graph = DependencyGraph(
            scope=scope,
            dataset_version=dataset_version,
            nodes=nodes,
            definitions=tuple(definitions),
            references=tuple(references),
        )
        cycles = _find_cycles(initial_graph)
        for cycle in cycles:
            diagnostics.append(
                _diagnostic(
                    DependencyGraphDiagnosticCode.DEPENDENCY_CYCLE,
                    kind=DependencyDiagnosticKind.STRUCTURAL,
                    cycle=cycle,
                    reason_codes=(ReasonCode.UNSUPPORTED_CASE,),
                    detail="strongly connected dependency component detected",
                )
            )
        graph = DependencyGraph(
            scope=scope,
            dataset_version=dataset_version,
            nodes=nodes,
            definitions=tuple(definitions),
            references=tuple(references),
            cycles=cycles,
        )
        ordered_diagnostics = tuple(sorted(diagnostics, key=_diagnostic_key))
        return DependencyGraphBuildResult(
            graph=graph,
            diagnostics=ordered_diagnostics,
            requires_human_review=any(
                diagnostic.requires_human_review for diagnostic in ordered_diagnostics
            ),
        )


def _constraint(target: CourseIdentity, rule: AcademicRule) -> DependencyConstraint:
    return DependencyConstraint(
        target_course=target,
        rule_id=rule.rule_id,
        expression=rule.expression,
        approval_status=rule.approval_status,
        verification_status=rule.verification_status,
        critical_for_planner=rule.critical_for_planner,
        provenance=rule.provenance,
    )


def _definition(
    target: CourseIdentity,
    dependency_coverage: DependencyCoverageStatus,
    eligibility_status: RuleSetStatus,
    constraints: tuple[DependencyConstraint, ...],
    reason_codes: tuple[ReasonCode, ...],
) -> DependencyDefinition:
    return DependencyDefinition(
        target_course=target,
        dependency_coverage=dependency_coverage,
        eligibility_rule_set_status=eligibility_status,
        constraints=constraints,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
    )


def _analyze_expression(
    expression: RuleExpression,
    *,
    path: tuple[int, ...] = (),
    positive: bool = True,
) -> _ExpressionAnalysis:
    if isinstance(expression, AndExpression):
        analyses = tuple(
            _analyze_expression(child, path=path + (index,), positive=positive)
            for index, child in enumerate(expression.children)
        )
        return _ExpressionAnalysis(
            all_positive_references=frozenset(
                reference
                for analysis in analyses
                for reference in analysis.all_positive_references
            ),
            definitely_required_references=frozenset(
                reference
                for analysis in analyses
                for reference in analysis.definitely_required_references
            ),
            occurrences=tuple(
                occurrence
                for analysis in analyses
                for occurrence in analysis.occurrences
            ),
            contains_unsupported=any(
                analysis.contains_unsupported for analysis in analyses
            ),
        )

    if isinstance(expression, OrExpression):
        analyses = tuple(
            _analyze_expression(child, path=path + (index,), positive=positive)
            for index, child in enumerate(expression.children)
        )
        required = set(analyses[0].definitely_required_references)
        for analysis in analyses[1:]:
            required.intersection_update(analysis.definitely_required_references)
        return _ExpressionAnalysis(
            all_positive_references=frozenset(
                reference
                for analysis in analyses
                for reference in analysis.all_positive_references
            ),
            definitely_required_references=frozenset(required),
            occurrences=tuple(
                occurrence
                for analysis in analyses
                for occurrence in analysis.occurrences
            ),
            contains_unsupported=any(
                analysis.contains_unsupported for analysis in analyses
            ),
        )

    if isinstance(expression, NotExpression):
        return _analyze_expression(
            expression.operand,
            path=path + (0,),
            positive=not positive,
        )

    if isinstance(expression, (CoursePassedExpression, CourseCompletedExpression)):
        occurrence = _ReferenceOccurrence(
            course=expression.course,
            external=None,
            path=path,
            positive=positive,
        )
        if not positive:
            return _ExpressionAnalysis(frozenset(), frozenset(), (occurrence,))
        return _ExpressionAnalysis(
            all_positive_references=frozenset({expression.course}),
            definitely_required_references=frozenset({expression.course}),
            occurrences=(occurrence,),
        )

    if isinstance(expression, CourseCurrentlyRegisteredExpression):
        return _ExpressionAnalysis(
            frozenset(),
            frozenset(),
            (
                _ReferenceOccurrence(
                    course=expression.course,
                    external=None,
                    path=path,
                    positive=False,
                ),
            ),
        )

    if isinstance(expression, UnsupportedExpression):
        course = _parse_optional_course_id(expression.course_id)
        external = None
        if course is None:
            reference = expression.course_code or expression.code
            if reference is not None:
                external = ExternalDependencyReference(
                    source_type=expression.source_type,
                    reference=reference,
                    condition_note=expression.condition_note,
                )
        return _ExpressionAnalysis(
            frozenset(),
            frozenset(),
            (
                _ReferenceOccurrence(
                    course=course,
                    external=external,
                    path=path,
                    positive=False,
                ),
            )
            if course is not None or external is not None
            else (),
            contains_unsupported=True,
        )

    return _ExpressionAnalysis(
        frozenset(),
        frozenset(),
        (),
        contains_unsupported=False,
    )


def _reference_from_occurrence(
    *,
    target: CourseIdentity,
    rule: AcademicRule,
    occurrence: _ReferenceOccurrence,
    required_courses: frozenset[CourseIdentity],
    course_map: dict[CourseIdentity, Course],
    invalid_course_ids: set[CourseIdentity],
    rule_scope_valid: bool,
) -> DependencyReference:
    if occurrence.external is not None:
        return DependencyReference(
            target_course=target,
            dependency=occurrence.external,
            rule_id=rule.rule_id,
            relation_kind=DependencyRelationKind.EXTERNAL,
            expression_path=occurrence.path,
            traversable=False,
            node_present=False,
            approval_status=rule.approval_status,
            verification_status=rule.verification_status,
            critical_for_planner=rule.critical_for_planner,
            provenance=rule.provenance,
        )

    assert occurrence.course is not None
    in_scope = (
        occurrence.course.regulation is target.regulation
        and occurrence.course.program == target.program
    )
    positive = occurrence.positive and rule_scope_valid and in_scope
    if positive:
        relation_kind = (
            DependencyRelationKind.REQUIRED
            if occurrence.course in required_courses
            else DependencyRelationKind.ALTERNATIVE
        )
    else:
        relation_kind = DependencyRelationKind.UNRESOLVED
    return DependencyReference(
        target_course=target,
        dependency=occurrence.course,
        rule_id=rule.rule_id,
        relation_kind=relation_kind,
        expression_path=occurrence.path,
        traversable=positive,
        node_present=(
            occurrence.course in course_map
            and occurrence.course not in invalid_course_ids
            and in_scope
        ),
        approval_status=rule.approval_status,
        verification_status=rule.verification_status,
        critical_for_planner=rule.critical_for_planner,
        provenance=rule.provenance,
    )


def _append_reference_diagnostics(
    diagnostics: list[DependencyGraphDiagnostic],
    reference: DependencyReference,
    *,
    target: CourseIdentity,
    rule: AcademicRule,
) -> None:
    dependency = reference.dependency
    if isinstance(dependency, ExternalDependencyReference):
        diagnostics.append(
            _diagnostic(
                DependencyGraphDiagnosticCode.EXTERNAL_REFERENCE,
                kind=DependencyDiagnosticKind.SOURCE_COVERAGE,
                target_course=target,
                rule_id=rule.rule_id,
                provenance=rule.provenance,
                external_reference=dependency,
                reason_codes=(ReasonCode.UNSUPPORTED_RULE,),
                detail="reference is not a canonical Planning CourseIdentity",
            )
        )
        return
    if (
        dependency.regulation is not target.regulation
        or dependency.program != target.program
    ):
        diagnostics.append(
            _diagnostic(
                DependencyGraphDiagnosticCode.CROSS_SCOPE_REFERENCE,
                kind=DependencyDiagnosticKind.STRUCTURAL,
                target_course=target,
                dependency_course=dependency,
                rule_id=rule.rule_id,
                provenance=rule.provenance,
                reason_codes=_scope_reasons_for_pair(target, dependency),
                detail="canonical reference is outside the target graph scope",
            )
        )
    elif not reference.node_present:
        diagnostics.append(
            _diagnostic(
                DependencyGraphDiagnosticCode.UNKNOWN_NODE,
                kind=DependencyDiagnosticKind.SOURCE_COVERAGE,
                target_course=target,
                dependency_course=dependency,
                rule_id=rule.rule_id,
                provenance=rule.provenance,
                reason_codes=(ReasonCode.MISSING_REQUIRED_DATA,),
                detail="canonical reference is absent from the supplied graph universe",
            )
        )
    if dependency == target:
        diagnostics.append(
            _diagnostic(
                DependencyGraphDiagnosticCode.SELF_DEPENDENCY,
                kind=DependencyDiagnosticKind.STRUCTURAL,
                target_course=target,
                dependency_course=dependency,
                rule_id=rule.rule_id,
                provenance=rule.provenance,
                detail="course directly references itself",
            )
        )


def _find_cycles(graph: DependencyGraph) -> tuple[DependencyCycle, ...]:
    positive = _adjacency(graph, required_only=False)
    required = _adjacency(graph, required_only=True)
    required_components = _cyclic_components(required)
    positive_components = _cyclic_components(positive)
    cycles: list[DependencyCycle] = []
    required_sets: set[frozenset[CourseIdentity]] = set()
    for members in required_components:
        member_set = frozenset(members)
        required_sets.add(member_set)
        cycles.append(
            DependencyCycle(
                members=members,
                kind=CycleKind.MANDATORY,
                rule_ids=_cycle_rule_ids(graph, member_set, required_only=True),
                representative_path=_representative_path(required, member_set),
            )
        )
    for members in positive_components:
        member_set = frozenset(members)
        if member_set in required_sets:
            continue
        cycles.append(
            DependencyCycle(
                members=members,
                kind=CycleKind.REFERENCE,
                rule_ids=_cycle_rule_ids(graph, member_set, required_only=False),
                representative_path=_representative_path(positive, member_set),
            )
        )
    return tuple(
        sorted(
            cycles,
            key=lambda item: (
                item.kind.value,
                tuple(member.course_id for member in item.members),
            ),
        )
    )


def _adjacency(
    graph: DependencyGraph,
    *,
    required_only: bool,
) -> dict[CourseIdentity, tuple[CourseIdentity, ...]]:
    adjacency: dict[CourseIdentity, set[CourseIdentity]] = {}
    for reference in graph.references:
        if not reference.traversable or not isinstance(
            reference.dependency, CourseIdentity
        ):
            continue
        if not graph.has_node(reference.target_course) or not graph.has_node(
            reference.dependency
        ):
            continue
        if (
            required_only
            and reference.relation_kind is not DependencyRelationKind.REQUIRED
        ):
            continue
        # Edges point from prerequisite to dependent for graph traversal.
        adjacency.setdefault(reference.dependency, set()).add(reference.target_course)
        adjacency.setdefault(reference.target_course, set())
    return {
        node: tuple(sorted(neighbors, key=lambda item: item.course_id))
        for node, neighbors in adjacency.items()
    }


def _cyclic_components(
    adjacency: dict[CourseIdentity, tuple[CourseIdentity, ...]],
) -> tuple[tuple[CourseIdentity, ...], ...]:
    if not adjacency:
        return ()
    reverse: dict[CourseIdentity, list[CourseIdentity]] = {
        node: [] for node in adjacency
    }
    for node, neighbors in adjacency.items():
        for neighbor in neighbors:
            reverse.setdefault(neighbor, []).append(node)
    reverse_tuple = {
        node: tuple(sorted(neighbors, key=lambda item: item.course_id))
        for node, neighbors in reverse.items()
    }
    order: list[CourseIdentity] = []
    visited: set[CourseIdentity] = set()
    for start in sorted(adjacency, key=lambda item: item.course_id):
        if start in visited:
            continue
        stack: list[tuple[CourseIdentity, int]] = [(start, 0)]
        visited.add(start)
        while stack:
            node, index = stack[-1]
            neighbors = adjacency.get(node, ())
            if index < len(neighbors):
                neighbor = neighbors[index]
                stack[-1] = (node, index + 1)
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append((neighbor, 0))
            else:
                order.append(node)
                stack.pop()

    components: list[tuple[CourseIdentity, ...]] = []
    visited.clear()
    for start in reversed(order):
        if start in visited:
            continue
        component: list[CourseIdentity] = []
        stack = [start]
        visited.add(start)
        while stack:
            node = stack.pop()
            component.append(node)
            for neighbor in reversed(reverse_tuple.get(node, ())):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        component_tuple = tuple(sorted(component, key=lambda item: item.course_id))
        if len(component_tuple) > 1 or component_tuple[0] in adjacency.get(
            component_tuple[0], ()
        ):
            components.append(component_tuple)
    return tuple(sorted(components, key=lambda item: tuple(x.course_id for x in item)))


def _representative_path(
    adjacency: dict[CourseIdentity, tuple[CourseIdentity, ...]],
    members: frozenset[CourseIdentity],
) -> tuple[CourseIdentity, ...]:
    start = min(members, key=lambda item: item.course_id)
    if start in adjacency.get(start, ()):
        return (start, start)
    for first in adjacency.get(start, ()):
        if first not in members:
            continue
        queue: deque[tuple[CourseIdentity, tuple[CourseIdentity, ...]]] = deque(
            [(first, (start, first))]
        )
        visited = {start, first}
        while queue:
            node, path = queue.popleft()
            if node == start:
                return path
            for neighbor in adjacency.get(node, ()):
                if neighbor not in members:
                    continue
                if neighbor == start:
                    return path + (start,)
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + (neighbor,)))
    return (start,)


def _cycle_rule_ids(
    graph: DependencyGraph,
    members: frozenset[CourseIdentity],
    *,
    required_only: bool,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                reference.rule_id
                for reference in graph.references
                if reference.traversable
                and isinstance(reference.dependency, CourseIdentity)
                and reference.target_course in members
                and reference.dependency in members
                and (
                    not required_only
                    or reference.relation_kind is DependencyRelationKind.REQUIRED
                )
            }
        )
    )


def _parse_optional_course_id(value: str | None) -> CourseIdentity | None:
    if value is None:
        return None
    try:
        return CourseIdentity.parse(value)
    except ValueError:
        return None


def _scope_reasons(
    scope: DependencyGraphScope, identity: CourseIdentity
) -> tuple[ReasonCode, ...]:
    reasons: list[ReasonCode] = []
    if identity.regulation is not scope.regulation:
        reasons.append(ReasonCode.WRONG_REGULATION)
    if identity.program != scope.program:
        reasons.append(ReasonCode.WRONG_PROGRAM)
    return tuple(reasons)


def _scope_reasons_for_pair(
    target: CourseIdentity,
    dependency: CourseIdentity,
) -> tuple[ReasonCode, ...]:
    reasons: list[ReasonCode] = []
    if dependency.regulation is not target.regulation:
        reasons.append(ReasonCode.WRONG_REGULATION)
    if dependency.program != target.program:
        reasons.append(ReasonCode.WRONG_PROGRAM)
    return tuple(reasons)


def _rule_scope_reasons(
    target: CourseIdentity,
    rule: AcademicRule,
) -> tuple[ReasonCode, ...]:
    reasons: list[ReasonCode] = []
    if rule.regulation is not target.regulation:
        reasons.append(ReasonCode.WRONG_REGULATION)
    if rule.program != target.program:
        reasons.append(ReasonCode.WRONG_PROGRAM)
    return tuple(reasons)


def _diagnostic(
    code: DependencyGraphDiagnosticCode,
    *,
    kind: DependencyDiagnosticKind,
    target_course: CourseIdentity | None = None,
    dependency_course: CourseIdentity | None = None,
    rule_id: str | None = None,
    provenance: Provenance | None = None,
    external_reference: ExternalDependencyReference | None = None,
    cycle: DependencyCycle | None = None,
    reason_codes: tuple[ReasonCode, ...] = (),
    detail: str | None = None,
) -> DependencyGraphDiagnostic:
    return DependencyGraphDiagnostic(
        code=code,
        kind=kind,
        target_course=target_course,
        dependency_course=dependency_course,
        rule_id=rule_id,
        provenance=provenance,
        external_reference=external_reference,
        cycle=cycle,
        reason_codes=reason_codes,
        detail=detail,
    )


def _diagnostic_key(item: DependencyGraphDiagnostic) -> tuple[object, ...]:
    return (
        item.code.value,
        item.target_course.course_id if item.target_course else "",
        item.dependency_course.course_id if item.dependency_course else "",
        item.rule_id or "",
        item.external_reference.reference if item.external_reference else "",
        tuple(member.course_id for member in item.cycle.members) if item.cycle else (),
    )
