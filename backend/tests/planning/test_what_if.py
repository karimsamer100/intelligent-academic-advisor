from __future__ import annotations

from dataclasses import replace

from backend.app.planning.domain.planning import LoadPreference
from backend.app.planning.domain.projection import AcademicStateLayer
from backend.app.planning.domain.scenario import (
    CourseOutcomeScenario,
    ExcludeCourseScenario,
    PlanningPreferenceScenario,
    WhatIfPlanningRequest,
)
from backend.app.planning.domain.student_history import AttemptOutcome, AttemptPurpose
from backend.app.planning.scenario.service import WhatIfEvaluationService

from backend.tests.planning.test_multi_semester_planner import (
    cid,
    course,
    planner,
    request,
    requirement,
    rule_set,
)


def test_course_outcome_scenario_uses_ephemeral_hypothetical_state() -> None:
    target = course("CSE341")
    baseline_request = request(
        (target,),
        (requirement(target.identity, 1),),
        rule_sets=(rule_set(target.identity),),
    )
    what_if = WhatIfEvaluationService(planner()).evaluate(
        WhatIfPlanningRequest(
            baseline=baseline_request,
            scenarios=(
                CourseOutcomeScenario(
                    cid("CSE341"),
                    AttemptOutcome.PASSED,
                    purpose=AttemptPurpose.INITIAL,
                ),
            ),
        )
    )

    assert what_if.baseline.initial_state.fact_layer is AcademicStateLayer.OBSERVED
    assert what_if.scenario.initial_state.fact_layer is AcademicStateLayer.HYPOTHETICAL
    assert (
        baseline_request.initial_student.pass_status(cid("CSE341")).value
        == "KNOWN_FALSE"
    )


def test_exclude_course_scenario_changes_selection_without_marking_failure() -> None:
    target = course("CSE341")
    result = WhatIfEvaluationService(planner()).evaluate(
        WhatIfPlanningRequest(
            baseline=request(
                (target,),
                (requirement(target.identity, 1),),
                rule_sets=(rule_set(target.identity),),
            ),
            scenarios=(ExcludeCourseScenario(target.identity),),
        )
    )

    assert result.scenario.steps[-1].plan.selected_courses == ()
    assert (
        result.scenario.initial_state.pass_status(target.identity).value
        == "KNOWN_FALSE"
    )
    assert target.identity in result.delta.removed_courses


def test_preference_scenario_changes_planning_policy_not_student_truth() -> None:
    first = course("CSE341")
    second = course("CSE342")
    baseline = request(
        (first, second),
        (requirement(first.identity, 1), requirement(second.identity, 2)),
        rule_sets=(rule_set(first.identity), rule_set(second.identity)),
    )
    result = WhatIfEvaluationService(planner()).evaluate(
        WhatIfPlanningRequest(
            baseline=baseline,
            scenarios=(
                PlanningPreferenceScenario(
                    replace(
                        baseline.preferences,
                        load_preference=LoadPreference.LIGHT,
                    )
                ),
            ),
        )
    )

    assert result.scenario.initial_state == baseline.initial_student
    assert (
        result.scenario.steps[0].plan.preferences.load_preference
        is LoadPreference.LIGHT
    )
    assert (
        result.to_dict()
        == WhatIfEvaluationService(planner())
        .evaluate(
            WhatIfPlanningRequest(
                baseline=baseline,
                scenarios=(
                    PlanningPreferenceScenario(
                        replace(
                            baseline.preferences,
                            load_preference=LoadPreference.LIGHT,
                        )
                    ),
                ),
            )
        )
        .to_dict()
    )
