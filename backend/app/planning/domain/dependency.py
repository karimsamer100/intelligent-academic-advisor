"""Immutable dependency-graph contracts for structural academic analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .course import Course, CourseIdentity, Program, Regulation
from .eligibility import RuleSetStatus
from .expressions import RuleExpression
from .lifecycle import ApprovalStatus, VerificationStatus
from .provenance import Provenance
from .reasons import ReasonCode
from .version import DatasetVersion


class DependencyCoverageStatus(StrEnum):
    """Coverage of course-to-course dependency semantics for one target."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class DependencyRelationKind(StrEnum):
    """Meaning of one derived dependency-reference occurrence."""

    REQUIRED = "REQUIRED"
    ALTERNATIVE = "ALTERNATIVE"
    UNRESOLVED = "UNRESOLVED"
    EXTERNAL = "EXTERNAL"


class DependencyDiagnosticKind(StrEnum):
    """Broad category of a graph construction diagnostic."""

    STRUCTURAL = "STRUCTURAL"
    SOURCE_COVERAGE = "SOURCE_COVERAGE"


class DependencyGraphDiagnosticCode(StrEnum):
    """Stable graph-specific construction and data-quality codes."""

    DUPLICATE_NODE = "DUPLICATE_NODE"
    DUPLICATE_RELATION = "DUPLICATE_RELATION"
    UNKNOWN_NODE = "UNKNOWN_NODE"
    CROSS_SCOPE_REFERENCE = "CROSS_SCOPE_REFERENCE"
    RULE_TARGET_MISMATCH = "RULE_TARGET_MISMATCH"
    SELF_DEPENDENCY = "SELF_DEPENDENCY"
    DEPENDENCY_CYCLE = "DEPENDENCY_CYCLE"
    INCOMPLETE_DEPENDENCY_DATA = "INCOMPLETE_DEPENDENCY_DATA"
    UNSUPPORTED_DEPENDENCY_EXPRESSION = "UNSUPPORTED_DEPENDENCY_EXPRESSION"
    EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"
    RULE_SET_UNAVAILABLE = "RULE_SET_UNAVAILABLE"


class CycleKind(StrEnum):
    """Whether an SCC is mandatory or only a broader positive reference cycle."""

    MANDATORY = "MANDATORY"
    REFERENCE = "REFERENCE"


@dataclass(frozen=True, slots=True)
class DependencyGraphScope:
    """Regulation/program boundary for one independent graph."""

    regulation: Regulation
    program: Program

    def __post_init__(self) -> None:
        if not isinstance(self.regulation, Regulation):
            raise TypeError("regulation must be a Regulation")
        if not isinstance(self.program, Program):
            raise TypeError("program must be a Program")

    def contains(self, identity: CourseIdentity) -> bool:
        """Return whether a canonical identity belongs to this graph scope."""

        return (
            identity.regulation is self.regulation and identity.program == self.program
        )


@dataclass(frozen=True, slots=True)
class DependencyNode:
    """A graph node backed by the existing minimal immutable ``Course``."""

    course: Course

    def __post_init__(self) -> None:
        if not isinstance(self.course, Course):
            raise TypeError("course must be a Course")

    @property
    def identity(self) -> CourseIdentity:
        return self.course.identity


@dataclass(frozen=True, slots=True)
class ExternalDependencyReference:
    """Opaque non-course reference preserved from an unsupported expression."""

    source_type: str
    reference: str
    condition_note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_type, str) or not self.source_type.strip():
            raise ValueError("source_type must be a non-empty string")
        if not isinstance(self.reference, str) or not self.reference.strip():
            raise ValueError("reference must be a non-empty string")
        if self.condition_note is not None and (
            not isinstance(self.condition_note, str) or not self.condition_note.strip()
        ):
            raise ValueError("condition_note must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class DependencyConstraint:
    """One target-bound rule expression; the expression is semantic truth."""

    target_course: CourseIdentity
    rule_id: str
    expression: RuleExpression | None
    approval_status: ApprovalStatus
    verification_status: VerificationStatus
    critical_for_planner: bool
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target_course, CourseIdentity):
            raise TypeError("target_course must be a CourseIdentity")
        if not isinstance(self.rule_id, str) or not self.rule_id.strip():
            raise ValueError("rule_id must be a non-empty string")
        if self.expression is not None and not isinstance(
            self.expression, RuleExpression
        ):
            raise TypeError("expression must be a RuleExpression or None")
        if not isinstance(self.approval_status, ApprovalStatus):
            raise TypeError("approval_status must be an ApprovalStatus")
        if not isinstance(self.verification_status, VerificationStatus):
            raise TypeError("verification_status must be a VerificationStatus")
        if not isinstance(self.critical_for_planner, bool):
            raise TypeError("critical_for_planner must be a bool")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")


@dataclass(frozen=True, slots=True)
class DependencyReference:
    """One occurrence derived from, but never replacing, a constraint tree."""

    target_course: CourseIdentity
    dependency: CourseIdentity | ExternalDependencyReference
    rule_id: str
    relation_kind: DependencyRelationKind
    expression_path: tuple[int, ...]
    traversable: bool
    node_present: bool
    approval_status: ApprovalStatus
    verification_status: VerificationStatus
    critical_for_planner: bool
    provenance: Provenance | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target_course, CourseIdentity):
            raise TypeError("target_course must be a CourseIdentity")
        if not isinstance(
            self.dependency, (CourseIdentity, ExternalDependencyReference)
        ):
            raise TypeError(
                "dependency must be a CourseIdentity or ExternalDependencyReference"
            )
        if not isinstance(self.rule_id, str) or not self.rule_id.strip():
            raise ValueError("rule_id must be a non-empty string")
        if not isinstance(self.relation_kind, DependencyRelationKind):
            raise TypeError("relation_kind must be a DependencyRelationKind")
        path = tuple(self.expression_path)
        if not all(isinstance(index, int) and index >= 0 for index in path):
            raise TypeError("expression_path must contain non-negative integers")
        if not isinstance(self.traversable, bool):
            raise TypeError("traversable must be a bool")
        if not isinstance(self.node_present, bool):
            raise TypeError("node_present must be a bool")
        if not isinstance(self.approval_status, ApprovalStatus):
            raise TypeError("approval_status must be an ApprovalStatus")
        if not isinstance(self.verification_status, VerificationStatus):
            raise TypeError("verification_status must be a VerificationStatus")
        if not isinstance(self.critical_for_planner, bool):
            raise TypeError("critical_for_planner must be a bool")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")
        if isinstance(self.dependency, ExternalDependencyReference):
            if self.relation_kind is not DependencyRelationKind.EXTERNAL:
                raise ValueError("external references must use EXTERNAL relation kind")
            if self.traversable or self.node_present:
                raise ValueError(
                    "external references cannot be graph-traversable nodes"
                )
        elif self.relation_kind is DependencyRelationKind.EXTERNAL:
            raise ValueError("EXTERNAL relation kind requires an external reference")
        object.__setattr__(self, "expression_path", path)


@dataclass(frozen=True, slots=True)
class DependencyDefinition:
    """All dependency constraints and both coverage dimensions for a target."""

    target_course: CourseIdentity
    dependency_coverage: DependencyCoverageStatus
    eligibility_rule_set_status: RuleSetStatus
    constraints: tuple[DependencyConstraint, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.target_course, CourseIdentity):
            raise TypeError("target_course must be a CourseIdentity")
        if not isinstance(self.dependency_coverage, DependencyCoverageStatus):
            raise TypeError("dependency_coverage must be a DependencyCoverageStatus")
        if not isinstance(self.eligibility_rule_set_status, RuleSetStatus):
            raise TypeError("eligibility_rule_set_status must be a RuleSetStatus")
        constraints = tuple(self.constraints)
        if not all(isinstance(item, DependencyConstraint) for item in constraints):
            raise TypeError("constraints must contain DependencyConstraint values")
        rule_ids = tuple(item.rule_id for item in constraints)
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("dependency constraint rule IDs must be unique")
        reasons = tuple(dict.fromkeys(self.reason_codes))
        if not all(isinstance(reason, ReasonCode) for reason in reasons):
            raise TypeError("reason_codes must contain only ReasonCode values")
        object.__setattr__(
            self,
            "constraints",
            tuple(sorted(constraints, key=lambda item: item.rule_id)),
        )
        object.__setattr__(self, "reason_codes", reasons)


@dataclass(frozen=True, slots=True)
class DependencyCycle:
    """One deterministic strongly connected component with a cycle."""

    members: tuple[CourseIdentity, ...]
    kind: CycleKind
    rule_ids: tuple[str, ...] = ()
    representative_path: tuple[CourseIdentity, ...] = ()

    def __post_init__(self) -> None:
        members = tuple(sorted(set(self.members), key=lambda item: item.course_id))
        if not members:
            raise ValueError("cycle must contain at least one member")
        if not isinstance(self.kind, CycleKind):
            raise TypeError("kind must be a CycleKind")
        rule_ids = tuple(sorted(set(self.rule_ids)))
        path = tuple(self.representative_path)
        if not all(isinstance(item, CourseIdentity) for item in path):
            raise TypeError("representative_path must contain CourseIdentity values")
        object.__setattr__(self, "members", members)
        object.__setattr__(self, "rule_ids", rule_ids)
        object.__setattr__(self, "representative_path", path)


@dataclass(frozen=True, slots=True)
class DependencyGraphDiagnostic:
    """Structured graph-build issue; not a natural-language explanation."""

    code: DependencyGraphDiagnosticCode
    kind: DependencyDiagnosticKind
    target_course: CourseIdentity | None = None
    dependency_course: CourseIdentity | None = None
    rule_id: str | None = None
    provenance: Provenance | None = None
    external_reference: ExternalDependencyReference | None = None
    cycle: DependencyCycle | None = None
    reason_codes: tuple[ReasonCode, ...] = ()
    detail: str | None = None
    requires_human_review: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.code, DependencyGraphDiagnosticCode):
            raise TypeError("code must be a DependencyGraphDiagnosticCode")
        if not isinstance(self.kind, DependencyDiagnosticKind):
            raise TypeError("kind must be a DependencyDiagnosticKind")
        for name in ("target_course", "dependency_course"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, CourseIdentity):
                raise TypeError(f"{name} must be a CourseIdentity or None")
        if self.rule_id is not None and (
            not isinstance(self.rule_id, str) or not self.rule_id.strip()
        ):
            raise ValueError("rule_id must be non-empty when provided")
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")
        if self.external_reference is not None and not isinstance(
            self.external_reference, ExternalDependencyReference
        ):
            raise TypeError(
                "external_reference must be an ExternalDependencyReference or None"
            )
        if self.cycle is not None and not isinstance(self.cycle, DependencyCycle):
            raise TypeError("cycle must be a DependencyCycle or None")
        reasons = tuple(dict.fromkeys(self.reason_codes))
        if not all(isinstance(reason, ReasonCode) for reason in reasons):
            raise TypeError("reason_codes must contain only ReasonCode values")
        if self.detail is not None and (
            not isinstance(self.detail, str) or not self.detail.strip()
        ):
            raise ValueError("detail must be non-empty when provided")
        if not isinstance(self.requires_human_review, bool):
            raise TypeError("requires_human_review must be a bool")
        object.__setattr__(self, "reason_codes", reasons)


@dataclass(frozen=True, slots=True)
class DependencyGraph:
    """Immutable structural graph with deterministic, student-independent queries."""

    scope: DependencyGraphScope
    dataset_version: DatasetVersion | None
    nodes: tuple[DependencyNode, ...] = ()
    definitions: tuple[DependencyDefinition, ...] = ()
    references: tuple[DependencyReference, ...] = ()
    cycles: tuple[DependencyCycle, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scope, DependencyGraphScope):
            raise TypeError("scope must be a DependencyGraphScope")
        if self.dataset_version is not None and not isinstance(
            self.dataset_version, DatasetVersion
        ):
            raise TypeError("dataset_version must be a DatasetVersion or None")
        nodes = tuple(self.nodes)
        definitions = tuple(self.definitions)
        references = tuple(self.references)
        cycles = tuple(self.cycles)
        if not all(isinstance(item, DependencyNode) for item in nodes):
            raise TypeError("nodes must contain DependencyNode values")
        if not all(isinstance(item, DependencyDefinition) for item in definitions):
            raise TypeError("definitions must contain DependencyDefinition values")
        if not all(isinstance(item, DependencyReference) for item in references):
            raise TypeError("references must contain DependencyReference values")
        if not all(isinstance(item, DependencyCycle) for item in cycles):
            raise TypeError("cycles must contain DependencyCycle values")
        node_ids = tuple(node.identity for node in nodes)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("graph node identities must be unique")
        definition_ids = tuple(item.target_course for item in definitions)
        if len(definition_ids) != len(set(definition_ids)):
            raise ValueError("graph definition targets must be unique")
        object.__setattr__(
            self,
            "nodes",
            tuple(sorted(nodes, key=lambda item: item.identity.course_id)),
        )
        object.__setattr__(
            self,
            "definitions",
            tuple(sorted(definitions, key=lambda item: item.target_course.course_id)),
        )
        object.__setattr__(
            self, "references", tuple(sorted(references, key=_reference_key))
        )
        object.__setattr__(self, "cycles", tuple(sorted(cycles, key=_cycle_key)))

    def has_node(self, course_id: CourseIdentity) -> bool:
        """Return whether the identity is in the supplied graph node universe."""

        _validate_identity(course_id)
        return any(node.identity == course_id for node in self.nodes)

    def definition_for(self, course_id: CourseIdentity) -> DependencyDefinition | None:
        """Return the target definition, including one with an unavailable source."""

        _validate_identity(course_id)
        return next(
            (item for item in self.definitions if item.target_course == course_id),
            None,
        )

    def direct_dependencies(
        self,
        course_id: CourseIdentity,
    ) -> tuple[DependencyReference, ...]:
        """Return canonical dependency occurrences, including unresolved ones."""

        _validate_identity(course_id)
        if not self.has_node(course_id):
            return ()
        return tuple(
            item
            for item in self.references
            if item.target_course == course_id
            and isinstance(item.dependency, CourseIdentity)
        )

    def external_references(
        self,
        course_id: CourseIdentity,
    ) -> tuple[DependencyReference, ...]:
        """Return opaque external references for one target."""

        _validate_identity(course_id)
        if not self.has_node(course_id):
            return ()
        return tuple(
            item
            for item in self.references
            if item.target_course == course_id
            and isinstance(item.dependency, ExternalDependencyReference)
        )

    def direct_dependents(
        self,
        course_id: CourseIdentity,
    ) -> tuple[DependencyReference, ...]:
        """Return positive traversable references pointing to this prerequisite."""

        _validate_identity(course_id)
        if not self.has_node(course_id):
            return ()
        return tuple(
            item
            for item in self.references
            if item.dependency == course_id
            and item.traversable
            and self.has_node(item.target_course)
        )

    def ancestors(self, course_id: CourseIdentity) -> tuple[CourseIdentity, ...]:
        """Return reachable positive prerequisites, sorted canonically."""

        _validate_identity(course_id)
        if not self.has_node(course_id):
            return ()
        discovered: set[CourseIdentity] = set()
        pending = [course_id]
        while pending:
            current = pending.pop()
            for reference in self.direct_dependencies(current):
                if not reference.traversable:
                    continue
                dependency = reference.dependency
                assert isinstance(dependency, CourseIdentity)
                if dependency in discovered:
                    continue
                discovered.add(dependency)
                if self.has_node(dependency):
                    pending.append(dependency)
        return tuple(sorted(discovered, key=lambda item: item.course_id))

    def descendants(self, course_id: CourseIdentity) -> tuple[CourseIdentity, ...]:
        """Return reachable positive dependents, sorted canonically."""

        _validate_identity(course_id)
        if not self.has_node(course_id):
            return ()
        discovered: set[CourseIdentity] = set()
        pending = [course_id]
        while pending:
            current = pending.pop()
            for reference in self.direct_dependents(current):
                dependent = reference.target_course
                if dependent in discovered:
                    continue
                discovered.add(dependent)
                if self.has_node(dependent):
                    pending.append(dependent)
        return tuple(sorted(discovered, key=lambda item: item.course_id))

    def has_path(self, source: CourseIdentity, target: CourseIdentity) -> bool:
        """Return whether a positive prerequisite path connects known nodes."""

        _validate_identity(source)
        _validate_identity(target)
        if not self.has_node(source) or not self.has_node(target):
            return False
        pending = [source]
        visited: set[CourseIdentity] = {source}
        while pending:
            current = pending.pop()
            for reference in self.direct_dependents(current):
                dependent = reference.target_course
                if dependent == target:
                    return True
                if dependent not in visited and self.has_node(dependent):
                    visited.add(dependent)
                    pending.append(dependent)
        return False


@dataclass(frozen=True, slots=True)
class DependencyGraphBuildResult:
    """Partial graph plus deterministic construction diagnostics."""

    graph: DependencyGraph
    diagnostics: tuple[DependencyGraphDiagnostic, ...] = ()
    requires_human_review: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.graph, DependencyGraph):
            raise TypeError("graph must be a DependencyGraph")
        diagnostics = tuple(self.diagnostics)
        if not all(isinstance(item, DependencyGraphDiagnostic) for item in diagnostics):
            raise TypeError("diagnostics must contain DependencyGraphDiagnostic values")
        if not isinstance(self.requires_human_review, bool):
            raise TypeError("requires_human_review must be a bool")
        object.__setattr__(self, "diagnostics", diagnostics)


def _validate_identity(course_id: CourseIdentity) -> None:
    if not isinstance(course_id, CourseIdentity):
        raise TypeError("course_id must be a CourseIdentity")


def _reference_key(reference: DependencyReference) -> tuple[object, ...]:
    dependency = (
        reference.dependency.course_id
        if isinstance(reference.dependency, CourseIdentity)
        else reference.dependency.reference
    )
    return (
        reference.target_course.course_id,
        dependency,
        reference.relation_kind.value,
        reference.rule_id,
        reference.expression_path,
    )


def _cycle_key(cycle: DependencyCycle) -> tuple[object, ...]:
    return (cycle.kind.value, tuple(item.course_id for item in cycle.members))
