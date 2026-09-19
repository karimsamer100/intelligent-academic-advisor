# Planning Engine foundation

This package owns framework-independent contracts for academic planning:
identity/value types, data lifecycle state, execution-safety policy, provenance,
reason codes, structured rule expressions, deterministic rule evaluation,
decision traces, result metadata, domain outcomes, and repository boundaries.

It does not own FastAPI or HTTP, ORM/PostgreSQL access, JSON loading outside
the narrow Academic Data adapter boundary, PDF extraction, RAG, LLM behavior,
frontend concerns, Degree Audit, or semester planning.

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
typed student context, explicitly covered attempt history, current
registrations, and an optionally selected academic snapshot into canonical
`StudentState`. A future repository or adapter must load and declare the
coverage of each collection; the builder never fetches records itself.
Attempts and registrations remain visible in immutable, deterministic order on
the resulting state.

The v2 canonical state is attempt-based. `CourseAttempt.outcome` uses the
typed vocabulary `PASSED`, `FAILED`, `WITHDRAWN`, `INCOMPLETE`, and `UNKNOWN`;
`INCOMPLETE` is a historical academic outcome and is not current
registration. `CourseAcademicRecord` keeps attempts and registrations while
exposing independent pass and registration facts plus a derived effective
course view. `attempt_number` is the current authoritative chronology field;
the builder never infers chronology from tuple order, term text, grades, or
record IDs.

History and registration coverage are explicit: `COMPLETE` permits a missing
course row to become a known false fact, while `PARTIAL` and `UNAVAILABLE`
make absence unknown. Unknown state is course-local and does not poison
unrelated courses. Failed, withdrawn, incomplete, and repeated attempts stay
in the complete history even when a later attempt determines the effective
pass fact. Explicit improvement outcomes are handled conservatively; unknown
purpose or missing chronology produces a course-local review diagnostic.

`passed_courses`, `failed_courses`, `withdrawn_courses`, `repeated_courses`,
and `current_courses` are derived compatibility views. `completed_courses` and
`COURSE_COMPLETED` temporarily alias successful/pass truth for builder-created
v2 state; they are not an independent canonical completion concept. The
builder never infers outcomes from grade text, opaque statuses, or positive
credits.

Exact and conflicting duplicate records, scope mismatches, contradictory
attempt facts, and missing coverage declarations fail closed with structured
diagnostics. Nonfatal incomplete or conflicting credit data leaves state
available with review diagnostics.

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
`StudentState` fact-query methods and their course-local unknown sets. A
`None` `passed_courses` value remains a backwards-compatible marker for legacy
states in which successful-pass data is globally unavailable; builder-created
v2 states always carry explicit coverage and per-course records. An empty
complete history therefore means known no pass, while an empty partial or
unavailable history is unknown.

Canonical course identities remain regulation/program scoped. Ordinary codes
remain strict uppercase tokens, while official Regulation 2023 ASU course
codes use the exact mixed-case form `R23:CAIE:ASUx31` (also `ASUx11` and
`ASUx48`). `SLOT:ASU_ELECTIVE_1` is an elective requirement placeholder, not a
`CourseIdentity`.

The current evaluator supports `COURSE_PASSED`, `COURSE_COMPLETED`,
`COURSE_CURRENTLY_REGISTERED`, `COURSE_CONCURRENT`, `MIN_EARNED_CREDITS`,
`MAX_EARNED_CREDITS`, `MIN_GPA`, and `MAX_GPA`. GPA thresholds are numeric
comparisons only; no GPA scale is assumed. `COURSE_CONCURRENT` is evaluated
only against an explicit target-aware projected-term context; current
registration never satisfies it. Unsupported entry, conditional, and
unresolved source concepts remain indeterminate. Academic level, academic
standing, term type, grade-order comparisons, requirement groups, electives,
and semester-level co-requisite semantics remain intentionally deferred until
their domain context exists.

Repository protocols expose domain-oriented read boundaries only; adapters are
outside this package.

## Eligibility orchestration

`EligibilityService` answers whether a supplied target course is academically
takeable from already-loaded `StudentState`, `Course`, and
`CourseEligibilityRuleSet` objects. `EligibilityContext` keeps registration
intent (`NORMAL`, `RETAKE_AFTER_FAILURE`, or `RETAKE_FOR_IMPROVEMENT`) separate
from evaluation horizon (`CURRENT` or `PROJECTED`). The canonical decision
vocabulary is `ELIGIBLE`, `INELIGIBLE`, `CONDITIONAL`,
`REQUIRES_ADVISOR_REVIEW`, `HUMAN_REVIEW_REQUIRED`, and `UNSUPPORTED`; the
legacy status and `eligible: bool | None` projection remain during migration.
Projected results carry immutable machine-readable future conditions such as
`CourseMustBePassedCondition`, never natural-language promises. Retake intent
does not authorize improvement registration; known passed improvement requests
remain advisor-review outcomes. The service owns no repositories, persistence,
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
Academic Data Foundation. It maps dataset metadata, courses, direct
prerequisite expressions, the supported typed subset of program requirements,
and elective pools into Planning types. `AcademicEligibilityDataSource`
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
`UnsupportedExpression` nodes; entry references are additionally represented
by an opaque `EntryRequirementReference` with `RequirementApplicability`
unknown until an authoritative applicability model exists. The evaluator
returns `INDETERMINATE` rather than dropping them. A missing formal
no-prerequisite signal, an unavailable corequisite artifact, or an
eligibility-relevant global rule outside this mapping slice keeps the supplied
rule set `INCOMPLETE`. `ALL_FOE` scope is not expanded into a specific program
without an authoritative applicability mapping, so unresolved scope remains a
reviewable coverage gap. The adapter does not synthesize the absent Regulation-23
101-CH gate or `ASUx11` record, and it does not turn blocked 18/21-CH source
records into current authority.

The result uses `eligible: bool | None`: `True` and `False` are definitive
answers, while `None` means the academic truth is unresolved. `ResultMetadata`
and the composed eligibility `DecisionTrace` preserve execution policy,
approval/verification state, reasons, provenance, and every meaningful rule
trace. Target-course lifecycle safety is assessed through the same
`ExecutionPolicy` used by `RuleEvaluator`; development results remain
non-authoritative.

## Program requirements foundation

`ProgramRequirement` is a governed wrapper around an optional immutable typed
definition. Definitions cover required course completion, zero-credit courses,
course counts from elective pools, concentration minimums, elective slots,
earned-credit thresholds, minimum GPA, field training, and total program
credits. Metadata-only legacy records remain non-evaluable until a typed
definition is available. `RequirementStage` distinguishes a registration gate
such as an explicit 101-CH fixture from the 144-CH program-completion total.

`ElectivePoolId`, `ElectiveSlotId`, and `ConcentrationId` are scoped
requirements identities and are deliberately not `CourseIdentity` values.
Slots are not fake courses; a slot may bind to an explicit pool or remain
unresolved. These contracts do not perform Degree Audit matching, GPA
calculation, course offering checks, or semester validation.

The deterministic Planning Engine is LLM-independent. A future orchestrator
may translate user language into these typed requests and ask an LLM to
explain structured results, but prompts, chat messages, model confidence, and
natural-language advice do not belong in this package.

## Dependency graph

`DependencyGraphBuilder` constructs a student-independent, regulation/program-
scoped graph from typed `Course` values and `CourseEligibilityRuleSet` values.
The original prerequisite expression stored in each immutable
`DependencyConstraint` remains the semantic source of truth; derived
`DependencyReference` values are only deterministic indexes for traversal and
analysis. `AND`/`OR` structure is never reconstructed from flattened edges.

For supported positive course references, the builder derives both all
references and references that are definitely required in every satisfying
branch. Thus `A AND (B OR C)` retains all three references but marks only `A`
as definitely required. Unsupported, conditional, external, negative, and
unresolved branches remain visible and make dependency coverage incomplete
where their semantics cannot be established safely.

Dependency coverage is intentionally separate from eligibility-rule coverage:
a course can have a complete direct course-dependency expression while its
eligibility rule set remains incomplete because global or otherwise unsupported
eligibility data is outside this graph slice. `COMPLETE` therefore never means
that a student is eligible. Missing nodes, cross-scope references, external
references, duplicate relations, and incomplete source data produce typed
diagnostics without fabricating courses or silently discarding relationships.

The graph exposes deterministic direct dependency/dependent lookups,
structural ancestors/descendants, positive-reference reachability, and
`has_node`. Traversal uses only positive canonical course references and does
not claim that every reachable course is individually mandatory. Cycle
detection uses strongly connected components on both the positive-reference
graph and the definitely-required graph, reporting `REFERENCE` versus
`MANDATORY` cycles without enumerating exponential simple paths. Lifecycle and
provenance stay attached to constraints and references; graph construction is
policy-neutral, so authoritative consumers still apply `ExecutionPolicy`.

The graph does not require `StudentState`, evaluate eligibility, perform
degree-audit matching, calculate planning scores, validate semesters, or own
repositories/adapters. The next intentionally deferred component is
student-specific degree-audit/requirement matching, followed later by
semester-aware planning.
