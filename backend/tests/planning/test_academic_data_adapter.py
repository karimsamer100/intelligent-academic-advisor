from dataclasses import FrozenInstanceError
import json
import shutil
from pathlib import Path

import pytest

from backend.app.planning.domain.course import CourseIdentity, Program, Regulation
from backend.app.planning.domain.eligibility import (
    EligibilityRequest,
    EligibilityStatus,
    RuleSetStatus,
)
from backend.app.planning.domain.evaluation import EvaluationOutcome
from backend.app.planning.domain.expressions import (
    AndExpression,
    CoursePassedExpression,
    UnsupportedExpression,
)
from backend.app.planning.domain.lifecycle import ApprovalStatus, VerificationStatus
from backend.app.planning.domain.reasons import ReasonCode
from backend.app.planning.domain.student import StudentState
from backend.app.planning.domain.version import DatasetVersion
from backend.app.planning.eligibility.service import EligibilityService
from backend.app.planning.policy import ExecutionMode, ExecutionPolicy
from backend.app.planning.repositories.adapters.academic_data_source import (
    AcademicEligibilityDataSource,
)
from backend.app.planning.repositories.adapters.academic_data_types import (
    AcademicDataConfig,
    AcademicDataDiagnostic,
    AcademicDataDiagnosticCode,
    AcademicDataSourceMode,
)
from backend.app.planning.repositories.adapters.academic_data_adapter import (
    JsonAcademicDataAdapter,
)
from backend.app.planning.rules.evaluator import RuleEvaluator


def test_source_mode_is_separate_from_execution_mode() -> None:
    config = AcademicDataConfig(
        package_root=Path("data/academic"),
        source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
    )

    assert config.source_mode is AcademicDataSourceMode.NORMALIZED_DEVELOPMENT


def test_diagnostic_is_typed_immutable_and_preserves_conflict_ids() -> None:
    diagnostic = AcademicDataDiagnostic(
        code=AcademicDataDiagnosticCode.CONFLICT_PRESENT,
        record_id="PRE-R23:CAIE:CSE486",
        conflict_ids=("CF-2023-019",),
        requires_human_review=True,
    )

    assert diagnostic.code is AcademicDataDiagnosticCode.CONFLICT_PRESENT
    assert diagnostic.conflict_ids == ("CF-2023-019",)
    with pytest.raises(FrozenInstanceError):
        diagnostic.code = AcademicDataDiagnosticCode.SOURCE_UNAVAILABLE


def test_normalized_load_keeps_usable_records_without_inventing_manifest_version() -> (
    None
):
    loaded = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=Path("data/academic"),
            source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
        )
    )

    assert loaded.value is not None
    assert loaded.dataset_version is None
    assert any(
        diagnostic.code is AcademicDataDiagnosticCode.MANIFEST_MISSING_OR_INVALID
        for diagnostic in loaded.diagnostics
    )


def test_verified_load_is_unavailable_without_normalized_fallback() -> None:
    loaded = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=Path("data/academic"),
            source_mode=AcademicDataSourceMode.VERIFIED_AUTHORITATIVE,
        )
    )

    assert loaded.value is None
    assert loaded.dataset_version is None
    assert any(
        diagnostic.code is AcademicDataDiagnosticCode.SOURCE_UNAVAILABLE
        for diagnostic in loaded.diagnostics
    )


def test_normalized_data_cannot_be_selected_for_authoritative_execution() -> None:
    loaded = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=Path("data/academic"),
            source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
            requested_execution_mode=ExecutionMode.AUTHORITATIVE,
        )
    )

    assert loaded.value is None
    assert any(
        diagnostic.code is AcademicDataDiagnosticCode.DATASET_MODE_MISMATCH
        for diagnostic in loaded.diagnostics
    )


def _load_normalized() -> JsonAcademicDataAdapter:
    loaded = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=Path("data/academic"),
            source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
        )
    )
    assert loaded.value is not None
    return loaded.value


def test_known_non_course_entities_are_diagnosed_but_do_not_poison_load() -> None:
    loaded = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=Path("data/academic"),
            source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
        )
    )

    slot_diagnostics = tuple(
        diagnostic
        for diagnostic in loaded.diagnostics
        if diagnostic.code is AcademicDataDiagnosticCode.UNSUPPORTED_ENTITY_KIND
    )

    assert loaded.value is not None
    assert len(slot_diagnostics) == 19
    assert all(
        ":SLOT:" in (diagnostic.record_id or "") for diagnostic in slot_diagnostics
    )
    assert loaded.value.corequisites_loaded is True
    assert loaded.value.corequisite_count == 0
    assert loaded.value.course_count == 169
    asu_lookup = loaded.value.get_course(CourseIdentity.parse("R23:CAIE:ASUx31"))
    assert asu_lookup.value is not None
    assert asu_lookup.value.approval_status is ApprovalStatus.BLOCKED
    assert not any(
        diagnostic.code is AcademicDataDiagnosticCode.MALFORMED_IDENTITY
        and diagnostic.record_id == "R23:CAIE:ASUx31"
        for diagnostic in loaded.diagnostics
    )


def test_cse112_course_and_direct_prerequisite_are_mapped_from_real_data() -> None:
    adapter = _load_normalized()
    target = CourseIdentity.parse("R18:CESS:CSE112")

    course_lookup = adapter.get_course(target)
    rule_lookup = adapter.get_eligibility_rules(target)

    assert course_lookup.value is not None
    assert course_lookup.value.identity == target
    assert course_lookup.value.approval_status is ApprovalStatus.SOURCE_VERIFIED
    assert course_lookup.value.verification_status is VerificationStatus.SOURCE_VERIFIED
    assert course_lookup.provenance[0].source_id == "SRC-CESS_NEW_BYLAW_2018_PDF"

    assert rule_lookup.value is not None
    assert rule_lookup.value.target_course == target
    assert rule_lookup.value.status is RuleSetStatus.INCOMPLETE
    assert len(rule_lookup.value.rules) == 1
    expression = rule_lookup.value.rules[0].expression
    assert isinstance(expression, AndExpression)
    assert expression.children == (
        CoursePassedExpression(CourseIdentity.parse("R18:CESS:CSE111")),
        CoursePassedExpression(CourseIdentity.parse("R18:CESS:CSE131")),
    )
    assert rule_lookup.provenance[0].rule_id == "PRE-R18:CESS:CSE112"
    assert any(
        diagnostic.code is AcademicDataDiagnosticCode.ELIGIBILITY_COVERAGE_GAP
        for diagnostic in rule_lookup.diagnostics
    )
    coverage = next(
        diagnostic
        for diagnostic in rule_lookup.diagnostics
        if diagnostic.code is AcademicDataDiagnosticCode.ELIGIBILITY_COVERAGE_GAP
        and diagnostic.record_id == "R18-016"
    )
    assert ReasonCode.UNAPPROVED_RULE in coverage.reason_codes


def test_cse486_preserves_blocked_conflicted_and_unresolved_prerequisite() -> None:
    adapter = _load_normalized()
    target = CourseIdentity.parse("R23:CAIE:CSE486")

    course_lookup = adapter.get_course(target)
    rule_lookup = adapter.get_eligibility_rules(target)

    assert course_lookup.value is not None
    assert course_lookup.value.approval_status is ApprovalStatus.BLOCKED
    assert (
        course_lookup.value.verification_status is VerificationStatus.NEEDS_VERIFICATION
    )
    assert any(
        diagnostic.code is AcademicDataDiagnosticCode.CONFLICT_PRESENT
        and "CF-2023-019" in diagnostic.conflict_ids
        for diagnostic in course_lookup.diagnostics
    )
    assert rule_lookup.value is not None
    assert rule_lookup.value.status is RuleSetStatus.INCOMPLETE
    assert rule_lookup.value.rules[0].approval_status is ApprovalStatus.BLOCKED
    assert (
        rule_lookup.value.rules[0].verification_status
        is VerificationStatus.NEEDS_VERIFICATION
    )
    expression = rule_lookup.value.rules[0].expression
    assert isinstance(expression, AndExpression)
    assert isinstance(expression.children[0], CoursePassedExpression)
    assert isinstance(expression.children[1], UnsupportedExpression)
    assert expression.children[1].source_type == "UNRESOLVED_CONDITION"
    assert expression.children[1].reason is not None
    assert any(
        diagnostic.code is AcademicDataDiagnosticCode.CONFLICT_PRESENT
        and "CF-2023-019" in diagnostic.conflict_ids
        for diagnostic in rule_lookup.diagnostics
    )
    assert any(
        diagnostic.code is AcademicDataDiagnosticCode.UNSUPPORTED_EXPRESSION
        for diagnostic in rule_lookup.diagnostics
    )


def test_conditional_and_entry_prerequisites_remain_unsupported() -> None:
    adapter = _load_normalized()

    conditional = adapter.get_eligibility_rules(CourseIdentity.parse("R23:CAIE:PHM111"))
    entry_requirement = adapter.get_eligibility_rules(
        CourseIdentity.parse("R18:CESS:PHM012")
    )

    assert conditional.value is not None
    assert conditional.value.status is RuleSetStatus.INCOMPLETE
    assert isinstance(conditional.value.rules[0].expression, AndExpression)
    assert all(
        isinstance(child, UnsupportedExpression)
        for child in conditional.value.rules[0].expression.children
    )
    assert entry_requirement.value is not None
    assert entry_requirement.value.status is RuleSetStatus.INCOMPLETE
    assert isinstance(
        entry_requirement.value.rules[0].expression, UnsupportedExpression
    )
    assert (
        entry_requirement.value.rules[0].expression.source_type == "ENTRY_REQUIREMENT"
    )
    assert ReasonCode.UNSUPPORTED_RULE in entry_requirement.value.reason_codes


def test_missing_prerequisite_row_is_incomplete_not_complete_empty() -> None:
    adapter = _load_normalized()
    lookup = adapter.get_eligibility_rules(CourseIdentity.parse("R18:CESS:CSE111"))

    assert lookup.value is not None
    assert lookup.value.status is RuleSetStatus.INCOMPLETE
    assert lookup.value.rules == ()
    assert ReasonCode.MISSING_REQUIRED_DATA in lookup.value.reason_codes
    assert any(
        diagnostic.code is AcademicDataDiagnosticCode.ELIGIBILITY_COVERAGE_GAP
        for diagnostic in lookup.diagnostics
    )


def test_supported_r23_prerequisite_can_be_complete_when_coverage_is_known() -> None:
    adapter = _load_normalized()
    lookup = adapter.get_eligibility_rules(CourseIdentity.parse("R23:CAIE:CSE142"))

    assert lookup.value is not None
    assert lookup.value.status is RuleSetStatus.COMPLETE
    assert len(lookup.value.rules) == 1
    assert isinstance(lookup.value.rules[0].expression, CoursePassedExpression)


def test_missing_corequisite_artifact_is_not_treated_as_empty(tmp_path: Path) -> None:
    package_root = tmp_path / "academic"
    normalized_root = package_root / "normalized"
    shutil.copytree(Path("data/academic/normalized"), normalized_root)
    (normalized_root / "corequisites.json").unlink()

    loaded = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=package_root,
            source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
        )
    )
    assert loaded.value is not None
    lookup = loaded.value.get_eligibility_rules(CourseIdentity.parse("R23:CAIE:CSE142"))

    assert loaded.value.corequisites_loaded is False
    assert lookup.value is not None
    assert lookup.value.status is RuleSetStatus.INCOMPLETE
    assert any(
        diagnostic.code is AcademicDataDiagnosticCode.ELIGIBILITY_COVERAGE_GAP
        and diagnostic.field == "corequisites"
        for diagnostic in lookup.diagnostics
    )


def test_invalid_manifest_does_not_invent_a_dataset_version(tmp_path: Path) -> None:
    package_root = tmp_path / "academic"
    normalized_root = package_root / "normalized"
    shutil.copytree(Path("data/academic/normalized"), normalized_root)
    (normalized_root / "dataset_manifest.json").write_text(
        json.dumps({"dataset_version": None}),
        encoding="utf-8",
    )

    loaded = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=package_root,
            source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
        )
    )

    assert loaded.value is not None
    assert loaded.dataset_version is None
    assert any(
        diagnostic.code is AcademicDataDiagnosticCode.MANIFEST_MISSING_OR_INVALID
        for diagnostic in loaded.diagnostics
    )


def test_incomplete_child_preserves_supported_siblings_in_expression_tree(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "academic"
    normalized_root = package_root / "normalized"
    shutil.copytree(Path("data/academic/normalized"), normalized_root)
    prerequisite_path = normalized_root / "prerequisites.json"
    prerequisites = json.loads(prerequisite_path.read_text(encoding="utf-8"))
    cse112 = next(
        record for record in prerequisites if record["course_id"] == "R18:CESS:CSE112"
    )
    cse112["expression"]["conditions"][1] = {}
    prerequisite_path.write_text(json.dumps(prerequisites), encoding="utf-8")

    loaded = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=package_root,
            source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
        )
    )
    assert loaded.value is not None
    lookup = loaded.value.get_eligibility_rules(CourseIdentity.parse("R18:CESS:CSE112"))

    assert lookup.value is not None
    assert len(lookup.value.rules) == 1
    expression = lookup.value.rules[0].expression
    assert isinstance(expression, AndExpression)
    assert isinstance(expression.children[0], CoursePassedExpression)
    assert isinstance(expression.children[1], UnsupportedExpression)
    assert expression.children[1].source_type == "INCOMPLETE_EXPRESSION"
    assert any(
        diagnostic.code is AcademicDataDiagnosticCode.INCOMPLETE_EXPRESSION
        for diagnostic in lookup.diagnostics
    )


def test_reordered_source_records_produce_identical_typed_lookups(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    source_root = Path("data/academic/normalized")
    shutil.copytree(source_root, first_root / "normalized")
    shutil.copytree(source_root, second_root / "normalized")
    for root in (first_root, second_root):
        for filename in ("courses.json", "prerequisites.json", "academic_rules.json"):
            path = root / "normalized" / filename
            values = json.loads(path.read_text(encoding="utf-8"))
            values.reverse()
            path.write_text(json.dumps(values), encoding="utf-8")

    first = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=first_root,
            source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
        )
    )
    second = JsonAcademicDataAdapter.load(
        AcademicDataConfig(
            package_root=second_root,
            source_mode=AcademicDataSourceMode.NORMALIZED_DEVELOPMENT,
        )
    )
    assert first.value is not None
    assert second.value is not None
    target = CourseIdentity.parse("R18:CESS:CSE112")
    assert first.value.get_course(target).value == second.value.get_course(target).value
    assert (
        first.value.get_eligibility_rules(target).value
        == second.value.get_eligibility_rules(target).value
    )
    assert (
        first.value.get_eligibility_rules(target).diagnostics
        == second.value.get_eligibility_rules(target).diagnostics
    )


def test_json_adapter_matches_narrow_typed_data_source_boundary() -> None:
    adapter = _load_normalized()

    assert isinstance(adapter, AcademicEligibilityDataSource)


def _adapter_eligibility_service() -> EligibilityService:
    """Use an explicitly test-scoped version, not an invented adapter version."""

    return EligibilityService(
        RuleEvaluator(
            ExecutionPolicy.development(),
            DatasetVersion("adapter-test-only"),
        )
    )


def _student_with_passes(*course_ids: str) -> StudentState:
    return StudentState(
        student_id="adapter-student",
        regulation=Regulation.R18,
        program=Program("CESS"),
        passed_courses=frozenset(
            CourseIdentity.parse(course_id) for course_id in course_ids
        ),
    )


def test_real_cse112_missing_direct_prerequisite_is_definitively_not_eligible() -> None:
    adapter = _load_normalized()
    target = CourseIdentity.parse("R18:CESS:CSE112")
    course = adapter.get_course(target).value
    rule_set = adapter.get_eligibility_rules(target).value

    assert course is not None
    assert rule_set is not None
    result = _adapter_eligibility_service().check(
        EligibilityRequest(
            student=_student_with_passes("R18:CESS:CSE111"),
            course=course,
            rule_set=rule_set,
        )
    )

    assert result.status is EligibilityStatus.NOT_ELIGIBLE
    assert result.eligible is False
    assert result.requires_human_review is True
    assert result.rule_results[0].outcome is EvaluationOutcome.UNSATISFIED
    assert ReasonCode.MISSING_REQUIRED_DATA in result.reason_codes


def test_real_cse112_satisfied_direct_prerequisite_remains_unresolved_by_coverage_gap() -> (
    None
):
    adapter = _load_normalized()
    target = CourseIdentity.parse("R18:CESS:CSE112")
    course = adapter.get_course(target).value
    rule_set = adapter.get_eligibility_rules(target).value

    assert course is not None
    assert rule_set is not None
    result = _adapter_eligibility_service().check(
        EligibilityRequest(
            student=_student_with_passes(
                "R18:CESS:CSE111",
                "R18:CESS:CSE131",
            ),
            course=course,
            rule_set=rule_set,
        )
    )

    assert result.status is EligibilityStatus.HUMAN_REVIEW_REQUIRED
    assert result.eligible is None
    assert result.rule_results[0].outcome is EvaluationOutcome.SATISFIED
    assert result.requires_human_review is True
