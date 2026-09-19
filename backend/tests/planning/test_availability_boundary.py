from __future__ import annotations

from backend.app.planning.domain.availability import (
    CourseOfferingCoverage,
    CourseOfferingFact,
    TimetableCoverage,
    TimetableFact,
)
from backend.app.planning.domain.course import CourseIdentity, Program, Regulation
from backend.app.planning.domain.planning import PlanningCoverageStatus
from backend.app.planning.domain.semester import TermType


def test_offering_boundary_preserves_known_not_offered_without_fabricating_data() -> (
    None
):
    identity = CourseIdentity(Regulation.R23, Program("CAIE"), "CSE341")
    coverage = CourseOfferingCoverage(
        PlanningCoverageStatus.COMPLETE,
        (CourseOfferingFact(identity, TermType.MAIN, False, term_id="T1"),),
    )

    assert coverage.fact_for(identity, TermType.MAIN, "T1").is_offered is False
    assert coverage.to_dict()["status"] == "COMPLETE"


def test_timetable_boundary_can_remain_unavailable() -> None:
    coverage = TimetableCoverage(PlanningCoverageStatus.UNAVAILABLE)
    assert coverage.facts == ()
    assert coverage.to_dict() == {"status": "UNAVAILABLE", "facts": []}


def test_timetable_fact_is_structured_but_not_a_schedule_solver() -> None:
    identity = CourseIdentity(Regulation.R23, Program("CAIE"), "CSE341")
    fact = TimetableFact(identity, TermType.SUMMER, None)

    assert fact.conflict_free is None
    assert fact.to_dict()["course"] == "R23:CAIE:CSE341"
