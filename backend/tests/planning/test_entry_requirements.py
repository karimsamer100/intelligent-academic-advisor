from __future__ import annotations

from backend.app.planning.domain.entry import (
    EntryRequirementReference,
    RequirementApplicability,
)
from backend.app.planning.domain.expressions import EntryRequirementExpression
from backend.app.planning.domain.course import Program, Regulation
from backend.app.planning.domain.expressions import CourseConcurrentExpression
from backend.app.planning.domain.expressions import UnsupportedExpression
from backend.app.planning.repositories.adapters.academic_expression_mapper import (
    map_expression,
)
from backend.app.planning.repositories.adapters.academic_json_loader import (
    RawExpression,
)


def test_entry_requirement_is_typed_and_not_a_course_expression() -> None:
    reference = EntryRequirementReference(
        code="ASU041",
        applicability=RequirementApplicability.UNKNOWN,
    )
    expression = EntryRequirementExpression(reference=reference)

    assert reference.applicability is RequirementApplicability.UNKNOWN
    assert expression.reference == reference
    assert expression.source_type == "ENTRY_REQUIREMENT"


def test_concurrent_source_expression_maps_to_typed_planning_expression() -> None:
    result = map_expression(
        RawExpression(
            source_type="CONCURRENT_COURSE",
            course_id="R23:CAIE:CSE392",
        ),
        regulation=Regulation.R23,
        program=Program("CAIE"),
        record_id="PR-493",
    )

    assert isinstance(result.expression, CourseConcurrentExpression)
    assert result.contains_unsupported is False


def test_concurrent_source_course_code_mismatch_is_not_silently_accepted() -> None:
    result = map_expression(
        RawExpression(
            source_type="CONCURRENT_COURSE",
            course_id="R23:CAIE:CSE392",
            course_code="CSE493",
        ),
        regulation=Regulation.R23,
        program=Program("CAIE"),
        record_id="PR-493",
    )

    assert isinstance(result.expression, UnsupportedExpression)
    assert result.contains_unsupported is True
