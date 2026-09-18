# Planning Engine foundation

This package owns framework-independent contracts for academic planning:
identity/value types, data lifecycle state, execution-safety policy, provenance,
reason codes, structured rule expressions, deterministic rule evaluation,
decision traces, result metadata, domain outcomes, and repository boundaries.

It does not own FastAPI or HTTP, ORM/PostgreSQL access, JSON loading outside
the narrow Academic Data adapter boundary, PDF extraction, RAG, LLM behavior, frontend concerns, or complete course
eligibility, degree audit, or semester planning.

## Core contracts

- Course identities are canonical and scoped by regulation and program, for
  example `R23:CAIE:CSE341`. A bare course code is not globally unique.
- `VerificationStatus` and `ApprovalStatus` are separate. Source verification
  records evidence quality; approval status determines whether academic data is
  safe to use for authoritative decisions.
- The current foundation maps persisted `verification_status` values to
  `VerificationStatus` and persisted `approval_status` values to
  `ApprovalStatus` without inference. In particular, persisted
  `SOURCE_VERIFIED` approval is retained as a non-approved compatibility state;
  `CONFLICTED` is a safety state for conflict reports and is never inferred.
- `AUTHORITATIVE` execution requires safe approved critical data. `DEVELOPMENT`
  execution may exercise suitable non-final data, but results remain explicitly
  non-authoritative. `BLOCKED`, `CONFLICTED`, and superseded data fail closed in
  both modes.
- `ReasonCode` values are machine-readable and intentionally contain no
  human-language message catalog.
- `Provenance` preserves rule/source/page and verification/approval context for
  later decisions.
- Immutable `DecisionTrace` trees represent structured rule outcomes and child
  evaluations without generating natural-language explanations.
- `ResultMetadata` is composed into future eligibility, audit, and planning
  results so safety context is not duplicated across result models.

## Student state construction

`StudentStateBuilder` is the single framework-independent boundary that turns
typed student context, complete available course-attempt history, current
registrations, and an optionally selected academic snapshot into canonical
`StudentState`. A future repository or adapter must load the complete history;
the builder never fetches records itself. Attempts and registrations remain in
immutable, deterministic order on the resulting state.

For the current Academic Data Foundation, `passed_courses` contains courses
with at least one internally consistent attempt whose explicit `passed` fact is
`True`. `completed_courses` currently derives from that same fact, but remains
a separate field so a future authoritative contract can distinguish successful
completion from passing. Failed and withdrawn attempts are preserved as
historical facts and do not populate either set. The builder never infers
outcomes from grade text, opaque statuses, or positive credits.

Missing pass facts are represented per course by
`unknown_pass_status_courses` and `unknown_completion_status_courses`; they do
not poison known facts for unrelated courses. With complete history, a course
outside the known or unknown sets is known not to have the corresponding fact.
Exact and conflicting duplicate records, scope mismatches, and contradictory
attempt facts fail closed with structured diagnostics. Nonfatal incomplete or
conflicting credit data leaves state available with review diagnostics.

An `AcademicSnapshot` is selected by the upstream adapter and its GPA, earned
credits, registered credits, academic level, standing, and track are passed
through without calculation. Snapshot earned credits take precedence over
safe distinct-course attempt-credit derivation; disagreement is retained as a
review diagnostic. GPA scale, repeat policy, grade replacement, and other
regulation-specific interpretation remain outside the builder.

Builder diagnostics describe input/state quality and are not `DecisionTrace`
nodes. Rule evaluation later produces decision traces for academic logic.

## Structured rule evaluation

Rules are represented as immutable expression trees. `AND`, `OR`, and `NOT`
compose leaf expressions recursively; `RuleEvaluator` walks the tree as a
pure operation over an already-loaded `StudentState` and produces a complete
machine-readable `DecisionTrace` that mirrors the expression tree.

Evaluation uses three outcomes: `SATISFIED`, `UNSATISFIED`, and
`INDETERMINATE`. Missing information is not treated as an academic failure:
for example, a GPA rule with `StudentState.gpa is None` is indeterminate and
requires review. Unsupported expressions and rules without an executable
expression fail closed in the same structured way.

Expression logic is separate from `AcademicRule` lifecycle metadata. The rule
record carries approval, verification, scope, and provenance; expressions only
describe logic. `COURSE_PASSED` reads the explicit
`StudentState.passed_courses` field and its course-local unknown set, while
`COURSE_COMPLETED` reads `completed_courses` and its corresponding unknown set.
A `None` `passed_courses` value remains a backwards-compatible marker that
successful-pass data is globally unavailable; an empty set means it is known
that no courses have been passed when no course-local unknown marker applies.

The current evaluator supports `COURSE_PASSED`, `COURSE_COMPLETED`,
`COURSE_CURRENTLY_REGISTERED`, `MIN_EARNED_CREDITS`, `MAX_EARNED_CREDITS`,
`MIN_GPA`, and `MAX_GPA`. GPA thresholds are numeric comparisons only; no GPA
scale is assumed. Academic level, academic standing, term type, grade-order
comparisons, requirement groups, electives, and advanced co-requisite
semantics remain intentionally deferred until their domain context exists.

Repository protocols expose domain-oriented read boundaries only; adapters are
outside this package.

## Eligibility orchestration

`EligibilityService` answers whether a supplied target course is currently
academically takeable from already-loaded `StudentState`, `Course`, and
`CourseEligibilityRuleSet` objects. It owns no repositories, persistence,
framework, JSON loading, semester planning, or natural-language explanation.

`CourseEligibilityRuleSet.target_course` is the binding between a selected rule
collection and its target course. The current `AcademicRule` contract does not
claim that binding; a future repository/Academic Data adapter must select the
correct records before constructing the rule set. A `COMPLETE` empty rule set
means the caller explicitly established that no applicable rules exist within
the modeled contract. `INCOMPLETE` and `UNAVAILABLE` rule sets cannot produce
definitive eligibility.

Eligibility combines independent supplied rules conjunctively while preserving
each expression tree unchanged for `RuleEvaluator`. A known unsatisfied rule
produces `NOT_ELIGIBLE`; missing, conflicted, blocked, or otherwise
indeterminate academic truth remains unresolved and carries review metadata.
Unsupported concepts such as minimum-grade, concurrent-course, and
semester-level co-requisite semantics must not be silently ignored.

## Academic Data adapter boundary

`repositories/adapters/` contains the narrow JSON consumer for the current
Academic Data Foundation. It maps only dataset metadata, courses, and direct
prerequisite expressions into Planning types. `AcademicEligibilityDataSource`
is the small typed boundary that a future PostgreSQL-backed source can replace.
Raw JSON records never reach `EligibilityService` or `RuleEvaluator`.
The adapter selects records before constructing a
`CourseEligibilityRuleSet`; its `target_course` is the trust binding because
`AcademicRule` does not carry a target-course field.

`NORMALIZED_DEVELOPMENT` and `VERIFIED_AUTHORITATIVE` are source tiers, not
execution modes. Normalized data may be loaded for development only; it is
never silently promoted to authoritative data, and verified data is never
silently replaced by normalized data. The current repository has no verified
export or trusted manifest, so the adapter reports verified data as
unavailable and exposes no fabricated dataset version.

Known elective-slot records are diagnosed as unsupported entities and are not
indexed as `Course` values. Direct prerequisite trees are preserved without
flattening. Source nodes such as conditional course requirements, opaque entry
requirements, and unresolved conditions become immutable
`UnsupportedExpression` nodes; the evaluator returns `INDETERMINATE` rather
than dropping them. A missing formal no-prerequisite signal, an unavailable
corequisite artifact, or an eligibility-relevant global rule outside this
mapping slice keeps the supplied rule set `INCOMPLETE`.

The result uses `eligible: bool | None`: `True` and `False` are definitive
answers, while `None` means the academic truth is unresolved. `ResultMetadata`
and the composed eligibility `DecisionTrace` preserve execution policy,
approval/verification state, reasons, provenance, and every meaningful rule
trace. Target-course lifecycle safety is assessed through the same
`ExecutionPolicy` used by `RuleEvaluator`; development results remain
non-authoritative.

The next intentionally deferred component is semester-aware co-requisite and
course-load validation, followed later by eligibility callers/adapters rather
than repository logic inside this package.
