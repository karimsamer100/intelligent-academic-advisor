# Academic Planning Engine — Full Development Guide

**Project:** Local Intelligent Academic Advisor  
**Task:** Academic Planning Engine  
**Status:** Ready to Implement  
**Goal:** Build a professional, testable, regulation-aware academic planning subsystem that can safely power eligibility, degree audit, course prioritization, semester planning, multi-semester planning, what-if analysis, explainability, and later personalization.

---

# 1. Purpose

The Academic Planning Engine is the core academic decision-support subsystem of the project.

It is responsible for answering questions such as:

- Can this student take Course X?
- Which prerequisites are missing?
- What courses become available after completing Course X?
- What degree requirements are complete or still missing?
- Is this semester plan academically valid?
- Which eligible courses should be prioritized?
- What happens if the student delays/fails/repeats a course?
- Can the student plan one or more future semesters safely?
- What choices reduce graduation delay?
- How can a lighter/heavier semester be constructed?
- What alternatives are valid?
- Does the case require human review?

The Planning Engine must produce **structured, explainable, reproducible results**.

It must not depend on an LLM to determine academic truth.

---

# 2. Core System Principle

```text
Student Request
      ↓
Backend / Orchestrator
      ↓
Student Academic State
      +
Verified Academic Data / Rules
      ↓
Academic Planning Engine
      ↓
Structured Verified Result
      ↓
RAG evidence if needed
      ↓
Local LLM explanation
      ↓
Student
```

Responsibilities are separated:

- **Planning Engine:** computes academic decisions.
- **Structured academic data:** contains rules and facts.
- **RAG:** retrieves official textual evidence/citations.
- **LLM:** understands and explains.
- **Backend/Orchestrator:** coordinates services.
- **Human advisor:** handles unresolved/exceptional cases.

---

# 3. Current Project Context

The Academic Data Foundation is already available for development.

Current assets include approximately:

- 188 courses
- Regulations 2018 and 2023
- prerequisite relations
- academic rules
- program requirements
- elective pools
- UEL mappings
- source registry
- schemas
- golden academic cases
- review/conflict information

The data is usable for development, but some academic conflicts are still awaiting final approval.

Important unresolved examples include:

- Regulation 2023 source conflicts
- incomplete CSE486 prerequisite
- CAIE technical-elective 18 CH vs 21 CH conflict
- some Regulation 2018 boundary/elective issues

Therefore:

> The engine must support uncertain, blocked, conflicted, and unapproved rules explicitly.

It must never guess a missing academic fact.

---

# 4. Non-Negotiable Design Rules

## 4.1 LLM is not academic authority

The engine must not call an LLM to decide:

- prerequisites
- eligibility
- credit limits
- graduation requirements
- plan validity
- degree progress

## 4.2 Regulation logic is data-driven

Avoid:

```python
if regulation == 23 and course_code == "CSE241":
    ...
```

Prefer generic rule models:

```text
COURSE_PASSED
MIN_GRADE
MIN_EARNED_CREDITS
COREQUISITE
MAX_CREDIT_LOAD
REQUIREMENT_CREDITS
COURSE_GROUP_COMPLETED
AND
OR
NOT
```

Regulation 18/23 differences should mostly live in data.

## 4.3 No direct database coupling

The domain engine should not contain raw PostgreSQL queries.

Use repository interfaces:

```text
PostgreSQL / JSON / in-memory fixtures
             ↓
       Repository Adapter
             ↓
       Planning Engine
```

This allows development before backend integration and makes testing simple.

## 4.4 No PDF/RAG logic inside the engine

The Planning Engine consumes structured academic data.

It does not parse PDFs or perform embedding/vector search.

## 4.5 Explainability is part of the engine

Every important result should expose:

- decision
- reasons
- violated/satisfied rules
- consequences
- alternatives when available
- warnings
- rule/source provenance
- human-review requirement

---

# 5. Recommended Package Structure

Use a modular package rather than one large `planning_engine.py`.

```text
backend/app/planning/
│
├── __init__.py
│
├── domain/
│   ├── course.py
│   ├── student.py
│   ├── rules.py
│   ├── requirements.py
│   ├── semester.py
│   ├── plan.py
│   └── results.py
│
├── repositories/
│   ├── course_repository.py
│   ├── rule_repository.py
│   ├── requirement_repository.py
│   ├── student_repository.py
│   └── adapters/
│       ├── in_memory.py
│       ├── json_adapter.py
│       └── postgres_adapter.py       # later/backend integration
│
├── rules/
│   ├── evaluator.py
│   ├── expressions.py
│   ├── validation.py
│   └── approval.py
│
├── eligibility/
│   ├── service.py
│   └── checks.py
│
├── graph/
│   ├── dependency_graph.py
│   └── analysis.py
│
├── audit/
│   ├── service.py
│   ├── progress.py
│   └── requirement_matching.py
│
├── semester/
│   ├── validator.py
│   ├── candidate_generator.py
│   └── builder.py
│
├── ranking/
│   ├── scorer.py
│   ├── objectives.py
│   └── weights.py
│
├── planner/
│   ├── single_semester.py
│   ├── multi_semester.py
│   ├── state_transition.py
│   └── search.py
│
├── scenarios/
│   ├── simulator.py
│   ├── delay.py
│   ├── failure.py
│   ├── repeat.py
│   └── workload.py
│
├── explainability/
│   ├── reasons.py
│   ├── provenance.py
│   └── formatter.py
│
├── review/
│   └── human_review.py
│
└── tests/
    ├── unit/
    ├── integration/
    ├── fixtures/
    └── golden/
```

The exact filenames may evolve, but keep these concerns separated.

---

# 6. Domain Model

The engine should work with typed domain objects.

Recommended minimum models:

## 6.1 Course

```text
course_id
course_code
course_name
regulation
program
credit_hours
course_type
level
semester/offering metadata if available
verification_status
approval_status
```

## 6.2 StudentState

```text
student_id
regulation
program
track (optional)
gpa (optional)
earned_credit_hours
completed_courses
course_attempts
current_courses
academic_level
academic_standing
preferences/goals
```

## 6.3 CourseAttempt

```text
course_id
attempt_number
term
academic_year
grade
passed
failed
withdrawn
repeated
credits_earned
```

## 6.4 AcademicRule

```text
rule_id
regulation
program
rule_type
conditions
result
approval_status
verification_status
source_id
source_page
```

## 6.5 ProgramRequirement

```text
requirement_id
regulation
program
requirement_type
requirement_group
required_courses
required_credit_hours
min_courses
max_courses
elective_pool_id
conditions
approval_status
```

## 6.6 ElectivePool

```text
pool_id
allowed_courses
required_number_of_courses
required_credit_hours
selection_rules
approval_status
```

## 6.7 PlanningGoal

Examples:

```text
NORMAL_PROGRESS
LIGHTER_LOAD
MAXIMIZE_PROGRESS
MINIMIZE_DELAY
MAINTAIN_GPA
IMPROVE_GPA
ACCELERATE_GRADUATION
TRACK_PROGRESS
```

The engine should allow multiple goals with priorities.

---

# 7. Rule Expression Model

The rule engine should support composable expressions.

Recommended primitives:

```text
COURSE_PASSED
COURSE_COMPLETED
COURSE_CURRENTLY_REGISTERED
MIN_GRADE
MIN_EARNED_CREDITS
MAX_EARNED_CREDITS
MIN_GPA
MAX_GPA
COREQUISITE
COURSE_GROUP_COMPLETED
REQUIREMENT_COMPLETED
TERM_TYPE
ACADEMIC_LEVEL
ACADEMIC_STANDING
```

Logical operators:

```text
AND
OR
NOT
```

Example:

```json
{
  "type": "AND",
  "conditions": [
    {
      "type": "COURSE_PASSED",
      "course_code": "CSE241"
    },
    {
      "type": "OR",
      "conditions": [
        {
          "type": "COURSE_PASSED",
          "course_code": "CSE281"
        },
        {
          "type": "MIN_EARNED_CREDITS",
          "value": 90
        }
      ]
    }
  ]
}
```

The evaluator should return more than `True/False`.

Return:

```text
satisfied
reason
failed_conditions
satisfied_conditions
rule_id
approval state
provenance
```

---

# 8. Approval / Conflict Handling

Academic correctness is more important than completeness.

Recommended statuses:

```text
EXTRACTED
SOURCE_VERIFIED
ACADEMICALLY_REVIEWED
APPROVED
BLOCKED
SUPERSEDED
CONFLICTED
```

For critical rules:

- `APPROVED` → may drive authoritative decisions.
- `BLOCKED` → must not drive a decision.
- `CONFLICTED` → requires human review.
- unapproved but usable development data → may be used only in development/test mode and must be flagged.

Recommended result behavior:

```json
{
  "status": "HUMAN_REVIEW_REQUIRED",
  "requires_human_review": true,
  "reason": "Critical prerequisite rule is unresolved",
  "rule_id": "R23-PR-CSE486"
}
```

Never silently choose one conflicting source.

---

# 9. Standard Result Contracts

Use structured result objects across the engine.

## 9.1 EligibilityResult

```json
{
  "course_id": "R23:CAIE:CSEXXX",
  "status": "ELIGIBLE",
  "eligible": true,
  "reasons": [],
  "warnings": [],
  "satisfied_rules": [],
  "failed_rules": [],
  "provenance": [],
  "requires_human_review": false
}
```

Possible statuses:

```text
ELIGIBLE
NOT_ELIGIBLE
ALREADY_COMPLETED
CURRENTLY_REGISTERED
BLOCKED_BY_UNVERIFIED_RULE
HUMAN_REVIEW_REQUIRED
UNSUPPORTED
```

## 9.2 AuditResult

```text
completed requirements
remaining requirements
completed credits
remaining credits
elective progress
mandatory-course progress
graduation readiness
warnings
provenance
```

## 9.3 SemesterValidationResult

```text
valid
total_credits
eligible_courses
invalid_courses
credit_rule_status
warnings
requires_human_review
```

## 9.4 PlanningResult

```text
recommended_plan
alternatives
reasons
warnings
consequences
score_breakdown
rule_provenance
requires_human_review
```

---

# 10. Academic State Builder

Create one canonical student academic state.

Responsibilities:

- normalize attempts
- determine passed/completed courses
- identify failed/repeated courses
- identify current registration
- compute earned credits if appropriate
- expose GPA/standing as provided by authoritative student data
- separate regulation/program context
- preserve relevant history

Do not let different engine modules independently reinterpret student history.

Use one state model as the single source of truth inside the Planning Engine.

---

# 11. Eligibility Engine

The first core service should answer:

```text
Can this student take this course now?
```

Checks may include:

- course exists
- correct regulation/program
- already completed
- currently registered
- prerequisite rules
- co-requisites
- minimum credits
- minimum grade requirements
- academic standing constraints
- credit/load constraints where relevant
- offering constraints when trusted offering data exists
- approval/conflict status

Conceptual API:

```python
check_eligibility(
    student: StudentState,
    course_id: str,
    context: EligibilityContext | None = None,
) -> EligibilityResult
```

Do not make eligibility depend on natural-language reasoning.

---

# 12. Dependency Graph

Represent prerequisite relationships as a directed graph.

Typical direction:

```text
prerequisite → dependent course
```

Needed operations:

```text
direct_prerequisites(course)
direct_dependents(course)
all_ancestors(course)
all_descendants(course)
unlock_count(course)
required_descendants(course)
critical_dependency_chain(course)
detect_cycles()
```

Use a simple Python graph library if useful; avoid adding a graph database unless a real need appears.

The graph should be constructed from structured prerequisite data.

---

# 13. Degree Audit

Audit must come before serious planning.

The audit service should determine:

- completed mandatory courses
- missing mandatory courses
- completed elective credits/courses
- remaining elective requirements
- completed requirement groups
- missing requirement groups
- total completed credits
- remaining credits
- graduation-project/training requirements if represented
- graduation readiness
- uncertain/blocked requirements

Conceptual API:

```python
audit_degree(student: StudentState) -> DegreeAuditResult
```

Important:

A planner should operate on **remaining requirements**, not blindly on all courses.

---

# 14. Semester Validation

A semester plan is not simply a list of eligible courses.

Validate:

- each course eligibility
- prerequisites/corequisites
- total credit load
- duplicate courses
- already completed courses
- regulation/program validity
- academic standing limits
- known offering constraints
- plan-level conflicts if modeled
- unresolved academic-rule dependencies

Conceptual API:

```python
validate_semester(
    student: StudentState,
    courses: list[str],
    term_context: TermContext
) -> SemesterValidationResult
```

Any manual plan edit should be revalidated.

---

# 15. Candidate Course Generation

For planning, first generate valid candidates.

Pipeline:

```text
remaining requirements
      ↓
candidate courses
      ↓
eligibility filtering
      ↓
valid candidates
```

Candidates may come from:

- missing mandatory courses
- eligible electives
- required prerequisite chain
- graduation requirement groups
- current planning horizon

Avoid ranking invalid courses.

---

# 16. Hard Constraints vs Soft Objectives

Separate these strongly.

## Hard Constraints

Examples:

- missing prerequisite
- missing co-requisite
- course already passed
- wrong regulation
- credit limit exceeded
- unapproved critical rule
- invalid requirement choice
- unavailable course if authoritative offering data exists

Invalid options are removed/rejected.

## Soft Objectives

Examples:

- unlock more future required courses
- reduce expected delay
- prioritize mandatory courses
- prioritize scarce/rare offerings
- lighter workload
- stronger academic progress
- maintain GPA
- improve GPA
- progress toward track
- student preferences

Soft objectives rank **valid** choices.

---

# 17. Ranking / Recommendation Layer

The first professional version can use explainable weighted scoring.

Example:

```text
score =
  mandatory_requirement_weight
+ dependency_unlock_weight
+ graduation_priority_weight
+ delay_reduction_weight
+ student_goal_weight
+ track_alignment_weight
- workload_penalty
- risk_penalty
```

Do not hard-code one opaque score with unexplained magic numbers.

Use:

```text
ScoreComponent
weight
raw_value
normalized_value
contribution
explanation
```

Return score breakdown.

Example:

```json
{
  "course": "CSEXXX",
  "score": 8.4,
  "components": [
    {
      "name": "required_course",
      "contribution": 3.0
    },
    {
      "name": "dependency_unlock",
      "contribution": 2.5
    }
  ]
}
```

Keep weights configurable.

---

# 18. Single-Semester Planner

The single-semester planner should:

1. build current student state
2. audit degree progress
3. generate candidate courses
4. remove invalid candidates
5. rank valid candidates
6. construct plan within credit constraints
7. validate complete semester
8. produce alternatives
9. return explanations

Inputs:

```text
student
term
planning goals
min/max desired credits
preferences
```

Outputs:

```text
recommended semester
alternative semester(s)
why these courses
warnings
remaining academic impact
```

Do not make the LLM select courses directly.

---

# 19. Multi-Semester Planning

Multi-semester planning should simulate academic state transitions.

Concept:

```text
State S0
  ↓ choose valid semester
State S1
  ↓ choose valid semester
State S2
  ↓ ...
```

Each transition should update:

- completed courses
- earned credits
- unlocked dependencies
- requirement progress
- planning horizon

Possible implementation strategies:

- greedy + revalidation initially
- beam search
- best-first search
- constraint optimization
- dynamic programming for specific subproblems

Do not commit to a complex solver before measuring need.

A professional implementation should allow the search strategy to be replaceable.

Suggested interface:

```python
plan_horizon(
    student,
    number_of_terms,
    goals,
    constraints
) -> MultiSemesterPlanningResult
```

---

# 20. State Transition Model

Create an explicit state transition function.

Example:

```python
next_state = apply_semester_result(
    current_state,
    completed_courses,
    grades=None
)
```

For deterministic planning before future grades are known, assume successful completion only when explicitly running a success scenario.

Do not silently assume future grades in every scenario.

Future outcomes should be scenario parameters.

---

# 21. What-If / Scenario Engine

The system should support scenario simulation.

Core scenarios:

```text
DELAY_COURSE
FAIL_COURSE
REPEAT_COURSE
TAKE_SUMMER_COURSE
LIGHTER_LOAD
HEAVIER_LOAD
ACCELERATE_GRADUATION
CHANGE_PREFERENCE
```

Later:

```text
PROGRAM_CHANGE
TRANSFER_CREDIT
TRACK_CHANGE
```

Example:

```python
simulate_delay(
    student,
    course_id,
    delay_terms=1
)
```

Return comparison:

```text
baseline plan
scenario plan
newly blocked courses
graduation impact
credit impact
warnings
```

---

# 22. Delay Analysis

Delay should be computed through dependencies and planning impact, not described vaguely.

Possible outputs:

```text
directly delayed courses
indirectly delayed courses
critical chain
earliest affected term
estimated additional terms if determinable
uncertainty
```

Avoid claiming a graduation delay if future offerings or data are insufficient.

Return uncertainty explicitly.

---

# 23. Failed / Repeated Course Handling

Student attempts must remain visible.

Rules may distinguish:

- failed
- passed after repeat
- repeated for improvement
- withdrawal
- current attempt

The planner should:

- re-open blocked dependency chains
- prioritize required failed courses where appropriate
- avoid treating failure as course completion
- support human review for regulation-specific repeat rules when unresolved

---

# 24. Workload-Aware Planning

Support goals such as:

```text
LIGHTER_LOAD
NORMAL_LOAD
MAXIMUM_PROGRESS
```

Do not invent course difficulty scores unless reliable data exists.

Initial workload can use safe signals such as:

- credit hours
- number of courses
- lab/contact hours if verified
- student-specified avoid/prefer list

Later, validated historical difficulty/performance data may be added.

---

# 25. GPA-Oriented Personalization

GPA-sensitive recommendation is a later ranking layer, not part of hard eligibility.

Support:

- maintain high GPA
- improve low GPA
- avoid overload

Do not claim a course will raise/lower GPA without validated evidence.

Use GPA mainly for:

- rule constraints
- credit-load rules
- planning preference
- ranking if validated performance signals become available

---

# 26. Track / Specialization Recommendation

Design the architecture so this can plug in later.

Inputs may include:

- completed courses
- grades
- track prerequisite/foundation courses
- track requirements
- student interests
- track progress

Pattern:

```text
Hard rules determine feasible tracks/options.
Scoring layer ranks valid options.
LLM explains.
```

Track recommendation should never be presented as an absolute judgment.

---

# 27. Human Review Detection

The engine should explicitly return `requires_human_review = true` when:

- rule is blocked
- rule is conflicted
- required data is missing
- exception approval is needed
- policy cannot be computed from current structured data
- student case falls outside encoded rules
- result depends on unresolved source authority

Recommended reason codes:

```text
UNVERIFIED_RULE
CONFLICTED_RULE
MISSING_REQUIRED_DATA
EXCEPTION_REQUIRED
UNSUPPORTED_CASE
AMBIGUOUS_REGULATION
```

---

# 28. Provenance

Every critical rule-based result should be traceable.

Recommended provenance object:

```text
rule_id
source_id
source_page
approval_status
verification_status
```

Example:

```json
{
  "rule_id": "R23-PR-CSE341",
  "source_id": "SRC-BYLAW-2023",
  "source_page": 123,
  "approval_status": "APPROVED"
}
```

Planning Engine provenance is structured-rule provenance.

RAG may later retrieve the source text/page for student-facing citation.

---

# 29. Explainability Contract

A professional planning result should make it possible to show:

```text
Recommendation
Reasons
Consequences
Alternatives
Warnings
Relevant rules
Human review state
```

Example:

```json
{
  "recommended": ["CSE341", "CSE352"],
  "reasons": [
    "CSE341 is a required course",
    "CSE341 unlocks two future mandatory courses"
  ],
  "consequences": [
    "Delaying CSE341 may block CSE441"
  ],
  "alternatives": [
    {
      "courses": ["CSE341", "CSE361"],
      "reason": "Lighter valid alternative"
    }
  ],
  "warnings": [],
  "requires_human_review": false
}
```

The engine explains through structured facts, not prose generation.

---

# 30. Repository Interfaces

Recommended interfaces:

```python
class CourseRepository:
    def get_course(...)
    def list_courses(...)
    def list_by_regulation(...)
    def get_prerequisites(...)
    def get_dependents(...)

class RuleRepository:
    def get_course_rules(...)
    def get_global_rules(...)
    def get_credit_rules(...)

class RequirementRepository:
    def get_program_requirements(...)
    def get_elective_pools(...)

class StudentRepository:
    def get_student_state(...)
```

During development:

```text
JSON / in-memory adapters
```

After backend/database integration:

```text
PostgreSQL adapters
```

The engine code should not change.

---

# 31. Integration Boundary

The Planning Engine should expose clean application-level services.

Possible service interface:

```python
class PlanningEngine:
    def check_eligibility(...)
    def audit_degree(...)
    def validate_semester(...)
    def compare_courses(...)
    def recommend_courses(...)
    def plan_semester(...)
    def plan_horizon(...)
    def simulate_scenario(...)
```

The backend/orchestrator calls these methods.

The engine should not know about HTTP routes.

---

# 32. Development Data Strategy

For now, use the normalized Academic Data Foundation already in the repository.

Important:

- do not treat unresolved conflicts as approved truth
- preserve approval/review state
- create adapters around the current normalized files
- do not tightly couple domain code to CSV/JSON field layout
- keep a mapping layer between raw normalized files and domain objects

Later, replace the adapter with PostgreSQL repositories.

---

# 33. Testing Strategy

Testing is mandatory from the beginning.

## Unit Tests

Test:

- expression evaluation
- AND/OR/NOT
- course passed
- minimum credits
- co-requisites
- approval handling
- dependency traversal
- score components
- state transitions

## Service Tests

Test:

- eligibility
- audit
- semester validation
- candidate generation
- plan generation
- what-if scenarios

## Golden Cases

Use academically reviewed golden cases where possible.

Each golden case should specify:

```text
student state
request
expected result
expected reason
expected provenance
expected human-review flag
```

Cases still pending academic review should not be treated as final correctness tests.

## Regression

Every fixed academic bug should become a regression test.

---

# 34. Important Edge Cases

Include tests for:

- course already completed
- current registration
- failed prerequisite
- repeated prerequisite
- AND prerequisites
- OR prerequisites
- nested prerequisite rules
- missing source/rule
- blocked rule
- conflicted rule
- wrong regulation
- elective choice
- credit cap
- minimum earned credits
- co-requisite
- prerequisite cycle
- empty student history
- near-graduation student
- low GPA
- high GPA
- delayed student
- transferred/program-changed state later

---

# 35. Performance

Correctness comes first.

Still, design for:

- prebuilt dependency graph per dataset version
- cached static rule structures
- no repeated full parsing of normalized data per request
- reusable audit state where safe
- deterministic results for identical inputs/data versions

Do not optimize prematurely.

---

# 36. Dataset Version Awareness

Every engine result should eventually know which academic dataset version produced it.

Recommended:

```text
dataset_version
rule_set_version
```

This makes recommendations reproducible.

Example:

```json
{
  "dataset_version": "1.0.0-dev",
  "result": "..."
}
```

---

# 37. Logging / Auditability

The engine should make it possible to record:

- operation requested
- student academic snapshot version
- dataset version
- rules evaluated
- result
- human-review flag

Do not log unnecessary sensitive student details.

Backend-level audit logging may persist these later.

---

# 38. Error Philosophy

Distinguish:

```text
INVALID_REQUEST
DATA_NOT_FOUND
UNSUPPORTED_RULE
CONFLICTED_RULE
UNAPPROVED_RULE
INTERNAL_ENGINE_ERROR
```

Do not turn academic uncertainty into a generic server error.

Academic uncertainty should be a valid structured outcome.

---

# 39. Professional Build Order

Do not treat this as nine disconnected mini-projects.

Build one extensible subsystem in this order:

## Foundation Block

Implement together:

- domain models
- repository interfaces/adapters
- rule expressions/evaluator
- student-state builder
- approval/conflict handling
- result contracts
- tests

## Academic Core Block

Then implement together:

- eligibility
- dependency graph
- degree audit
- semester validation

## Planning Block

Then:

- candidate generation
- ranking/scoring
- single-semester planning
- alternatives
- revalidation

## Advanced Planning Block

Then:

- state transitions
- multi-semester planning
- what-if scenarios
- delay/failure/repeat handling

## Personalization / Extension Block

Then:

- workload goals
- GPA-aware ranking
- track recommendation
- advisor-review signals

This sequence is for dependency management, not for building a throwaway MVP.

Everything should be designed as part of the final professional architecture from the beginning.

---

# 40. Initial Implementation Target

The first complete capability should support:

```text
Student state
+
Course
+
Structured academic rules
↓
Eligibility Engine
↓
Structured EligibilityResult
```

Then immediately expand to:

```text
Degree Audit
+
Dependency Graph
+
Semester Validation
```

The first end-to-end integration later should support:

```text
"Can I take Course X?"
```

Flow:

```text
Backend / Orchestrator
→ Student Profile
→ Planning Engine
→ EligibilityResult
→ RAG evidence/page
→ LLM explanation
```

---

# 41. What Not To Put Inside This Task

Do not implement:

- FastAPI routes as core planning logic
- PostgreSQL-specific queries inside domain services
- RAG ingestion/retrieval
- PDF parsing
- LLM prompts/tool calling
- frontend
- voice
- advisor dashboard
- automatic resolution of academic conflicts

Integration adapters can be added later without contaminating the domain engine.

---

# 42. Definition of Done — Professional Planning Engine

The full Planning Engine task is considered complete when the system can reliably:

- load a normalized student academic state
- evaluate generic academic rules
- handle prerequisites/corequisites
- determine eligibility
- expose rule provenance
- detect unapproved/conflicted academic data
- build and analyze dependency graphs
- perform degree audit/progress calculation
- validate a proposed semester
- generate valid course candidates
- rank valid choices explainably
- build a valid semester plan
- provide alternatives
- plan across multiple semesters
- revalidate state between semesters
- simulate delay/failure/repeat/workload scenarios
- identify human-review cases
- return structured machine-readable results
- pass unit/service/golden regression tests
- remain independent of LLM/RAG/UI/PostgreSQL implementation details

---

# 43. Expected Deliverables

The implementation should eventually deliver:

```text
planning package
domain models
repository interfaces
development adapters
rule evaluator
approval/conflict handling
student-state builder
eligibility engine
dependency graph
degree audit
semester validator
candidate generator
ranking/scoring
single-semester planner
multi-semester planner
scenario simulator
explainability/provenance
human-review detection
unit tests
golden/regression tests
developer README
```

---

# 44. Suggested README Examples

Include examples developers can run.

Example:

```python
student = student_repo.get_student_state("student-001")

result = engine.check_eligibility(
    student=student,
    course_id="R23:CAIE:CSE341",
)

print(result.status)
print(result.reasons)
```

And:

```python
plan = engine.plan_semester(
    student=student,
    goals=["MINIMIZE_DELAY"],
    desired_credits=15,
)
```

---

# 45. Final Engineering Principle

The Planning Engine should be built so that:

> **Changing the LLM does not change academic truth.**  
> **Changing the database does not require rewriting planning logic.**  
> **Changing a regulation updates data, not scattered conditional code.**  
> **Uncertain academic information produces review, not guesses.**  
> **Every recommendation can explain why it was produced.**

This subsystem is one of the main technical contributions of the project and should be treated as production-quality domain logic, even though the overall project is a graduation project.
