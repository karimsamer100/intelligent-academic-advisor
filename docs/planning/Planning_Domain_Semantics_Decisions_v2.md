# Planning Engine — Domain Semantics & Decisions v2

**Project:** Local Intelligent Academic Advisor  
**Primary scope:** Ain Shams University Faculty of Engineering — CAIE, Regulations 2023 and 2018  
**Document purpose:** Keep one implementation-facing record of the academic semantics, decisions, corrections, source hierarchy, and unresolved items discovered after reviewing the real code, the current CAIE course tree, the September 2023 bylaws, UEL material, Academic Data Foundation, and direct clarification of real student behavior.

**Status date:** 2026-09-19  
**Use this file before implementing any new Planning Engine feature.**

---

# 1. Why this document exists

The first Planning Engine foundation was intentionally conservative and generic. After inspecting the real implementation and then reviewing the actual CAIE study plan and bylaws, several assumptions were found to be too narrow for the final product.

This document records:

- what is now considered **locked / approved working semantics**;
- what was learned from the **official bylaws and current CAIE tree**;
- what was clarified from **real current CAIE student behavior**;
- which earlier assumptions must be **changed**;
- which topics are still **unresolved** and must not be guessed;
- how future implementation tasks should use these decisions.

The goal is to prevent future Codex/ChatGPT sessions from re-inventing academic semantics or silently making conflicting assumptions.

---

# 2. Status legend

Every rule or decision should be understood using one of these labels.

| Label | Meaning |
|---|---|
| **LOCKED** | Approved project-level decision; future implementation should follow it unless explicitly revised. |
| **SOURCE-CONFIRMED** | Supported by an official source such as the 2023 bylaws or the current CAIE study tree. |
| **USER-CONFIRMED** | Confirmed as current real behavior by a current Regulation-23 CAIE student. |
| **WORKING DECISION** | Chosen implementation semantics that are currently accepted but may evolve if stronger official evidence appears. |
| **UNRESOLVED** | Information is incomplete, contradictory, or not yet confirmed. The engine must fail closed / request review rather than guess. |
| **DEFERRED** | Known requirement intentionally postponed to a later implementation slice. |

---

# 3. Source hierarchy for the Planning Engine

## 3.1 Regulation 2023 CAIE

Use sources for different responsibilities rather than pretending there is one universal document.

### General academic regulations

**Primary source:** `Bylaw 2023.pdf`  
Use it for:

- study levels;
- registration load;
- GPA / academic warning;
- repeating and improvement;
- incomplete (`I`);
- withdrawal (`W`);
- graduation requirements;
- zero-credit general rules;
- field training;
- study duration;
- fee-related general rules;
- advisor authority;
- general 70% graduation-project threshold.

### Current CAIE cohort study structure

**Primary operational source:** `23P - CAIE - course tree.pdf`

For the current Regulation-23 CAIE cohort, use this tree for:

- recommended semester placement;
- current CAIE course sequence;
- normal course prerequisites;
- current graduation-project sequence;
- current CAIE elective slot positions.

When the current cohort tree differs from an older/general table in the large bylaws, the current tree is the working source for the current cohort's study-plan structure, while the disagreement must remain traceable in provenance.

### Do not delete conflicts

A newer operational value may supersede an older study-plan placement for runtime planning, but keep provenance/history instead of silently deleting the old source.

---

## 3.2 Regulation 2018

Regulation 2018 remains a separate rule set.

Do **not** copy Regulation-23 thresholds into Regulation 2018.

Examples already known to differ include:

- program duration;
- graduation-project earned-credit threshold;
- zero-credit requirements;
- technical-elective credit structure.

The Planning Engine should remain generic, but the rules/data must be regulation-scoped.

---

## 3.3 UEL

UEL is a parallel academic-progress system.

UEL documents may define:

- UEL modules;
- UEL level progression;
- module results;
- relationships between ASU courses and UEL modules.

However, the current Planning Engine will **not** become a detailed UEL-grade-calculation engine.

Use UEL primarily for:

- outstanding-module awareness;
- UEL level/progression risk;
- planning priority;
- warnings about delay;
- eventual award-readiness checks.

Official UEL module results should be preferred when available.

---

# 4. Core architectural principles that remain valid

The following earlier Planning Engine decisions remain correct.

## 4.1 LLM is not academic authority — LOCKED

The LLM may:

- converse with the student;
- explain results;
- ask for missing information;
- select Planning/RAG tools;
- summarize why a result occurred.

The LLM must **not** invent academic eligibility or override deterministic rules.

---

## 4.2 Deterministic Planning Engine — LOCKED

Academic decisions such as:

- prerequisite satisfaction;
- earned-credit gates;
- registration-load constraints;
- requirement completion;
- course-plan validation;

must be computed by deterministic Planning Engine logic.

---

## 4.3 Verification and academic approval are separate — LOCKED

Do not equate:

`SOURCE_VERIFIED`

with:

`APPROVED`

A record can be extracted correctly from a source while still awaiting academic approval.

---

## 4.4 Fail closed on unknown critical academic truth — LOCKED

Unknown or conflicting academic truth must never silently become:

- `True`;
- `False`;
- eligible;
- complete;
- satisfied.

Use structured unresolved/human-review outcomes.

---

## 4.5 Preserve provenance — LOCKED

Critical results should remain traceable to:

- rule ID;
- source/document;
- page where available;
- lifecycle / verification state;
- dataset version when available.

---

## 4.6 DecisionTrace remains useful — LOCKED

DecisionTrace should explain deterministic decisions.

It is different from:

- adapter diagnostics;
- data-quality diagnostics;
- conversational explanations.

---

# 5. Student academic state v2

This is the most important correction before Degree Audit.

## 5.1 Attempts are the historical source of truth — LOCKED

A student's relationship with a course must preserve individual attempts.

Conceptually:

```text
CourseAcademicRecord
├── attempt 1
├── attempt 2
├── ...
├── current registration
└── derived effective academic state
```

Do not reduce the history permanently into only:

```text
passed_courses = {...}
failed_courses = {...}
```

Those may remain compatibility/derived views.

---

## 5.2 Historical attempt outcomes

The Planning domain needs to distinguish at least:

```text
PASSED
FAILED
WITHDRAWN
INCOMPLETE
UNKNOWN
```

### `INCOMPLETE` is not `IN_PROGRESS`

**SOURCE-CONFIRMED**

In the 2023 bylaws, `I / Incomplete` is a specific official state: the student did not attend the final exam with an officially accepted excuse.

Therefore:

```text
IN_PROGRESS != INCOMPLETE
```

A course being studied now is represented by current registration / in-progress state, not by `I`.

---

## 5.3 Current registration is separate

A current registration means:

```text
IN_PROGRESS / CURRENTLY_REGISTERED
```

It does not mean the course has been passed.

Future projected planning may use it conditionally, but normal prerequisite truth still requires a pass unless the rule explicitly allows concurrency.

---

## 5.4 `Completed` is not a separate essential truth — WORKING DECISION

The current code has separate:

- `passed_courses`;
- `completed_courses`.

The current builder largely makes them equivalent.

For the real Planning domain, do **not** build important logic around an independent concept of:

```text
COMPLETED_BUT_NOT_PASSED
```

Important course facts are:

- passed;
- failed;
- withdrawn;
- incomplete;
- current/in-progress;
- unknown;
- repeated/improved.

`completed_courses` may survive temporarily as a compatibility view, but should not be an independent authoritative fact.

---

## 5.5 History coverage must be explicit — LOCKED

The old implicit assumption:

```text
attempts == ()
=> definitely no prior academic history
```

must be removed.

Introduce explicit coverage such as:

```text
COMPLETE
PARTIAL
UNAVAILABLE
```

Meaning:

```text
COMPLETE + no attempts
=> we know there are no attempts

PARTIAL/UNAVAILABLE + no supplied attempts
=> we do not know whether attempts exist
```

Missing data must not become `NOT_PASSED`.

Per-course uncertainty should remain local; one uncertain course must not poison unrelated courses.

---

# 6. Rule truth semantics

## 6.1 Three-valued evaluation remains correct — LOCKED

Rule evaluation outcomes:

```text
SATISFIED
UNSATISFIED
INDETERMINATE
```

These are **truth states for a rule**, not student grade labels.

Example:

```text
Rule: COURSE_PASSED(CSE141)
```

- evidence proves CSE141 passed -> `SATISFIED`;
- complete history proves not passed -> `UNSATISFIED`;
- history is incomplete/unknown -> `INDETERMINATE`.

Do not collapse unknown into false.

---

## 6.2 Normal prerequisite semantics — LOCKED

For a normal prerequisite such as:

```text
CSE241 requires CSE141
```

the default meaning is:

```text
COURSE_PASSED(CSE141)
```

Any passing grade is sufficient unless an explicit academic rule states a minimum prerequisite grade.

Do not infer a minimum grade from GPA or course marks.

---

## 6.3 GPA is not a normal prerequisite — LOCKED

GPA can affect:

- registration load;
- academic warning/probation;
- graduation readiness;
- other global rules.

It does not automatically make a specific course prerequisite fail.

---

# 7. Repeat and improvement semantics

## 7.1 Retake for improvement exists — SOURCE-CONFIRMED / USER-CONFIRMED

A student may repeat a course already passed in order to improve GPA.

Therefore the current universal rule:

```text
already passed -> ALREADY_COMPLETED -> cannot register
```

cannot remain the final eligibility model.

Future registration intent must distinguish:

```text
NORMAL_ENROLLMENT
RETAKE_AFTER_FAILURE
RETAKE_FOR_IMPROVEMENT
```

Administrative/advisor approval may still be required.

---

## 7.2 Official 2023 improvement behavior

From the bylaws:

- repeating a passed course for improvement is allowed;
- the higher grade is normally the one used;
- improvement attempts are limited, with specified exceptions;
- improvement after completing total program study hours is not allowed;
- an elective may be changed subject to advisor approval/program rules;
- if the student fails an improvement repeat, the previous grade is cancelled and the student becomes failed in that course;
- repeating an originally failed course has separate rules;
- the entire course assessment is repeated.

### Important implementation consequence

Do **not** derive effective pass state using only:

```python
any(attempt.passed for attempt in attempts)
```

because a later improvement attempt can change the effective academic state.

The canonical course-state builder must derive the **effective current state** from attempt history and known repeat purpose.

If the available data does not contain enough information to determine the effective state safely:

```text
effective status = UNKNOWN
```

with a diagnostic.

---

# 8. Earned credits

## 8.1 Earned credit means successfully earned — LOCKED

For Planning purposes:

```text
earned_credit_hours
```

are credits from successfully passed credit-bearing courses.

Not:

- registered credits;
- attempted credits;
- failed credits.

---

## 8.2 Avoid repeat double counting — LOCKED

The same academic course must not contribute earned credits twice because it was repeated.

---

## 8.3 Snapshot remains authoritative when present — WORKING DECISION

If a trusted academic snapshot provides total earned credits, keep the current rule:

```text
official snapshot earned credits
> locally derived attempt total
```

The locally derived total is useful for:

- diagnostics;
- consistency checking;
- fallback when safe.

Do not replace the official snapshot silently.

---

# 9. Course identity corrections

## 9.1 Official mixed-case ASU codes are real — SOURCE-CONFIRMED

Examples include:

```text
ASUx11
ASUx31
ASUx48
```

These are real course codes.

Therefore:

```text
R23:CAIE:ASUx31
```

must be a valid canonical identity.

---

## 9.2 Do not globally make course codes case-insensitive — LOCKED

Ordinary codes remain canonical, e.g.:

```text
CSE141
PHM111
ECE261
```

The parser should support the official ASUx pattern specifically rather than allowing arbitrary mixed-case course codes.

Canonical output must remain deterministic.

---

## 9.3 Real ASUx courses are not elective-slot pseudo-records — LOCKED

Distinguish:

```text
ASUx31
```

which is a real course,

from:

```text
SLOT:ASU_ELECTIVE_1
```

which is a requirement placeholder / elective slot.

Do not expand `CourseIdentity` so widely that SLOT records become ordinary courses.

---

# 10. Entry / placement requirements

## 10.1 Starred first-year conditions are not normal prerequisites — WORKING DECISION

Current CAIE tree contains values such as:

```text
ASU041*
PHM011*
```

These are treated for the current cohort as entry/foundation/placement conditions rather than normal course prerequisites.

Do not force the student to have a fake normal course attempt merely to satisfy them.

A future model should support something like:

```text
ENTRY_REQUIREMENT
FOUNDATION_REQUIREMENT
SATISFIED_BY_PLACEMENT
SATISFIED_BY_EXEMPTION
```

---

## 10.2 ASU041 current cohort behavior — USER-CONFIRMED

For the current Regulation-23 CAIE cohort:

- `ASU041 Technical English` is not treated as a normal active SIS course requirement;
- do not block Math/Physics registration because no ordinary `ASU041` course attempt exists.

The full 2023 bylaws still contain ASU041 as a formal zero-credit/placement-related item, so preserve provenance and do not erase the source conflict.

---

# 11. Current Regulation-23 CAIE study plan

**Working operational source:** `23P - CAIE - course tree.pdf`

Recommended CH totals in the current tree:

| Semester | CH |
|---|---:|
| 1 | 18 |
| 2 | 18 |
| 3 | 18 |
| 4 | 18 |
| 5 | 19 |
| 6 | 19 |
| 7 | 17 |
| 8 | 17 |

These semester totals are the recommended plan, not hard eligibility restrictions.

---

# 12. Recommended semester vs offering vs eligibility

These must remain three separate concepts.

```text
recommended_semester
!= actual_term_offering
!= prerequisite_eligibility
```

## Recommended semester

Where the official/current study plan places the course.

Used for planning guidance.

## Actual offering

Whether the course is actually open in a particular term.

This can vary depending on:

- demand;
- staff;
- resources;
- program decisions.

Do not hard-code the study-plan semester as the only term a course can be offered.

## Eligibility

Whether the student satisfies academic requirements to register.

A student may be academically eligible outside the recommended semester.

---

# 13. Registration load rules — Regulation 2023

**SOURCE-CONFIRMED**

Main semester maximum after advisor approval:

| Cumulative GPA | Maximum |
|---|---|
| `GPA >= 3.0` | 21 CH **or** 8 courses, whichever is greater |
| `2.0 <= GPA < 3.0` | 18 CH **or** 7 courses, whichever is greater |
| `GPA < 2.0` | 14 CH **or** 5 courses, whichever is greater |

Summer:

| GPA | Maximum |
|---|---|
| `GPA >= 3.0` | 9 CH or 3 courses, whichever is greater |
| `GPA < 3.0` | 8 CH or 2 courses, whichever is greater |

A graduation-enabling extra course may be allowed with advisor approval under the bylaw rules.

### Implementation rule

Do not simplify:

```text
GPA < 2 -> exactly five courses
```

The actual rule contains both credit-hour and course-count dimensions.

This belongs in semester validation/load policy, not ordinary prerequisite evaluation.

---

# 14. Study levels — Regulation 2023

**SOURCE-CONFIRMED**

For a 144-CH program:

```text
Freshman  : 0%   to <25%
Sophomore : 25%  to <50%
Junior    : 50%  to <75%
Senior    : 75%  to <100%
```

25% corresponds to 36 CH.

CAIE is an interdisciplinary major, and the bylaws permit interdisciplinary students to register higher-level courses without the specialized-major progression restrictions that apply elsewhere.

Therefore:

```text
not completing every lower-year course
```

does not automatically block every higher-year course.

Course prerequisites and other explicit rules remain the primary course-level constraints.

---

# 15. Graduation-project rules — Regulation 2023 CAIE

## 15.1 Earned-credit threshold — LOCKED WORKING RULE

For the current Regulation-23 CAIE model use:

```text
MIN_EARNED_CREDITS_FOR_GRADUATION_STAGE = 101
```

Reason:

- program total = 144 CH;
- bylaw general requirement = at least 70%;
- `144 * 0.70 = 100.8`;
- current material also shows the 101-CH threshold around graduation-project progression.

Use **101**, not 100.

---

## 15.2 Current cohort project sequence

Current CAIE tree:

```text
CSE392 CAIE Graduation Project Survey
CSE493 CAIE Graduation Project (1)
CSE494 CAIE Graduation Project (2)
```

Current tree states:

```text
CSE493 prerequisite = CSE392 OR concurrent
CSE494 prerequisite = CSE493
```

---

## 15.3 Concurrent semantics — LOCKED

For the current cohort:

```text
CSE493 is valid if:
    CSE392 was already passed
    OR
    CSE392 is registered in the same proposed semester
```

Do **not** model this as a plain mandatory prior `COURSE_PASSED(CSE392)`.

Do not remove the relationship either.

It is a true concurrent rule.

This requires proposed-semester context and therefore belongs in the future Semester Validator / Eligibility v2 context.

Example:

```text
Proposed semester:
CSE392
CSE493

CSE392 not previously passed

=> CSE493 may be valid because CSE392 is concurrent
```

But:

```text
Proposed semester:
CSE493 only

CSE392 never passed

=> invalid
```

---

# 16. CAIE technical electives

## 16.1 Number of technical electives — LOCKED

Regulation-23 CAIE:

```text
7 technical electives
```

---

## 16.2 Credit value — LOCKED / USER-CONFIRMED

Each CAIE technical elective is:

```text
3 CH
```

Therefore 7 selected electives naturally contribute:

```text
7 * 3 = 21 CH
```

Do not use the historical/contradictory `18 CH` total for current Regulation-23 CAIE computation.

### Important modeling decision

Represent the requirement primarily as:

```text
required_elective_courses = 7
each_selected_course_credit_hours = 3
```

and derive 21 CH.

Do not make an old conflicting aggregate number the primary rule.

---

## 16.3 Concentration rule — LOCKED

Student must complete at least:

```text
5 of the 7 technical electives
```

from one CAIE concentration.

The remaining two may be chosen from any concentration(s), subject to actual course offering and other academic rules.

The student does not need to formally declare a concentration first for our Planning model.

The system can infer concentration qualification from completed/selected courses.

Examples:

```text
6 Software + 1 Data Science => valid Software concentration
5 Software + 1 Data Science + 1 Distributed => valid Software concentration
7 Software => valid Software concentration
```

---

## 16.4 CAIE concentrations — SOURCE-CONFIRMED / USER-CONFIRMED

The four concentrations are:

1. Multimedia and Computer Graphics
2. Distributed and Mobile Computing
3. Software Product Lines
4. Data Science

Maintain regulation-specific course membership even if Regulation 2018 and 2023 overlap heavily.

Do not assume the membership list is universally identical between regulations.

---

## 16.5 Current elective slot placement

Current cohort tree places:

```text
Semester 5: CAIE Elective 1, 2
Semester 6: CAIE Elective 3
Semester 7: CAIE Elective 4, 5
Semester 8: CAIE Elective 6, 7
```

This is the recommended plan.

Moving an elective between semesters can happen operationally, but exceptions/availability may require advisor review.

Do not encode the slot semester as a rigid academic eligibility condition.

---

# 17. ASU electives

## 17.1 Elective slots are requirements, not fake courses — LOCKED

Examples:

```text
ASU Elective (1)
ASU Elective (2)
ASU Elective (3)
```

These represent elective requirements/slots.

Future Degree Audit should model:

```text
ElectiveSlot
ElectivePool
AllowedCourses
```

not:

```text
Course("ASU Elective 1")
```

---

## 17.2 A pool means

A **pool** is the set of real courses that are allowed to fulfill a specific elective requirement.

Example concept:

```text
ASU Elective Slot 1
    ↓
Pool A
    ↓
ASUx12 / ASUx13 / ...
```

Some ASU elective slots may have different allowed pools.

Do not assume all ASU elective slots are interchangeable unless the source explicitly says so.

---

## 17.3 Operational availability

ASU elective course availability can vary from semester to semester.

Sometimes only one of several possible electives is actually offered to a cohort.

Therefore:

```text
pool membership
!= term offering
```

The planner should eventually combine both.

---

# 18. Zero-credit requirements

## 18.1 General bylaw rule — SOURCE-CONFIRMED

Students must pass all applicable zero-credit courses in their program.

Zero-credit courses:

- contribute 0 CH;
- do not contribute to GPA;
- can still be graduation requirements.

---

## 18.2 ASUx11 Societal Issues — USER-CONFIRMED

`ASUx11 Societal Issues` exists for the current cohort and should be treated as a real zero-credit graduation requirement.

It must be passed before graduation.

---

## 18.3 ASU041 Technical English — current cohort exception

The large bylaw includes ASU041, but the current student-confirmed Regulation-23 CAIE behavior is that Technical English is not an active ordinary course requirement in the current cohort.

Therefore do not automatically create a graduation blocker based solely on absence of an ASU041 course attempt.

Keep it as a source/operational-version discrepancy until fully reconciled.

---

## 18.4 Other current zero-credit requirements — UNRESOLVED

There may be additional current zero-credit requirement changes.

Do not invent them.

Add them only when identified from:

- current SIS;
- current cohort documents;
- advisor/faculty confirmation;
- approved Academic Data.

---

# 19. Field training — Regulation 2023

**SOURCE-CONFIRMED**

General 2023 rules include:

```text
8 weeks field training
```

It is a graduation requirement.

Training is evaluated:

```text
PASS / FAIL
```

and does not contribute to cumulative GPA.

For interdisciplinary-major students, training can begin after satisfying the relevant freshman-credit threshold stated in the bylaws.

Future Degree Audit should model Field Training as a non-course program requirement, not as a normal credit-bearing course.

---

# 20. Academic warning and GPA

## 20.1 Academic warning

**SOURCE-CONFIRMED**

```text
Cumulative GPA < 2.0
=> Academic Warning
```

This is an academic-standing fact.

---

## 20.2 Graduation GPA

**SOURCE-CONFIRMED**

Graduation requires cumulative GPA:

```text
>= 2.0
```

after satisfying graduation requirements.

---

## 20.3 Keep concerns separate

Do not mix:

```text
course prerequisite
registration load
academic standing
graduation readiness
planning priority
```

They are separate rule categories.

---

# 21. UEL semantics

## 21.1 UEL and ASU progress are separate — LOCKED

A student may be at different effective positions in the two systems.

Conceptually:

```text
ASU progress
!= UEL progress
```

Example:

```text
ASU requirements for a year completed
UEL previous-level module still outstanding
```

The system must be able to represent both.

---

## 21.2 Do not overbuild grade mapping — LOCKED

The product does not need to expose or deeply compute every 60%/40% mapping detail for everyday planning.

Keep mappings available where useful for traceability, but focus the Planning layer on:

- which ASU courses relate to UEL;
- whether UEL modules are passed/outstanding;
- level progression;
- delay risk;
- planning priority.

---

## 21.3 Official UEL result should be preferred

If an official UEL module status/result is available, treat it as the authoritative UEL result.

Do not blindly derive UEL pass status from ASU course grades.

ASU course pass and UEL module pass are distinct.

---

## 21.4 UEL delay priority — WORKING PRODUCT REQUIREMENT

UEL-related courses/modules may deserve higher planning priority when delaying them risks:

- UEL level progression;
- outstanding modules;
- extra financial burden / later complications.

Do **not** implement this as an arbitrary magic weight.

Future prioritization should distinguish:

```text
hard academic constraint
UEL progression risk
financial risk
soft preference
```

Exact financial/deadline rules remain unresolved until sourced.

---

## 21.5 UEL exceptional progression — HUMAN REVIEW

If a student has an outstanding UEL module and progression depends on special/exceptional approval, surface:

```text
REQUIRES_UEL_OR_ADVISOR_REVIEW
```

Do not guess that the student definitely can or cannot progress.

---

# 22. Dependency Graph decisions

The Dependency Graph implementation remains useful.

## 22.1 Expression tree remains source of truth — LOCKED

Do not rebuild academic logic from flattened edges.

---

## 22.2 AND/OR reference extraction — LOCKED

The graph may derive:

```text
all_positive_references
definitely_required_references
```

Example:

```text
A AND (B OR C)
```

gives:

```text
all = {A, B, C}
definitely required = {A}
```

Example:

```text
(A AND B) OR (A AND C)
```

gives:

```text
all = {A, B, C}
definitely required = {A}
```

This is structural analysis only; the original expression remains authoritative.

---

## 22.3 Concurrent dependencies are not normal prerequisite edges — LOCKED

Example:

```text
CSE392 concurrent with CSE493
```

requires semester context.

Do not pretend concurrency is the same as:

```text
CSE392 must already be passed
```

---

## 22.4 Dependency coverage and eligibility coverage remain separate — LOCKED

A course may have complete direct course dependencies but incomplete global eligibility knowledge.

Do not collapse these concepts.

---

# 23. Academic Data Adapter decisions

The adapter remains responsible for translating external Academic Data into typed Planning objects.

## 23.1 Never silently drop unsupported rules — LOCKED

Unsupported expressions remain visible and make the relevant coverage incomplete.

---

## 23.2 Missing prerequisite row is not automatically “no prerequisite” — LOCKED

Until the data contract has a formal no-prerequisite signal:

```text
no row
!= known no prerequisites
```

Fail closed.

---

## 23.3 Elective slot records are not malformed courses — LOCKED

Known SLOT records are unsupported requirement entities, not ordinary Course identities.

---

## 23.4 Normalized vs verified data — LOCKED

- normalized data may be used for development;
- verified/approved runtime data is required for authoritative decisions;
- never silently fall back from verified to normalized.

---

# 24. Immediate code corrections required before Degree Audit

The following are now required before implementing Degree Audit.

## Task A — Student Academic State v2

Fix:

- attempt model;
- effective course state;
- explicit history coverage;
- incomplete vs in-progress;
- repeat/improvement awareness;
- earned-credit derivation;
- compatibility views.

---

## Task B — CourseIdentity correction

Support official mixed-case ASUx codes without allowing arbitrary invalid mixed-case identities.

---

## Task C — Eligibility / Registration v2

Must later distinguish:

```text
normal registration
retake after failure
retake for improvement
current eligibility
projected next-term eligibility
concurrent eligibility
```

Do not leave `ALREADY_COMPLETED` as a universal blocker.

---

## Task D — Program Requirements model

Before Degree Audit, create typed concepts for:

```text
CoreCourseRequirement
ElectivePoolRequirement
ElectiveSlot
ConcentrationRequirement
ZeroCreditRequirement
GraduationRequirement
FieldTrainingRequirement
```

Do not implement Degree Audit as:

```text
required_courses - passed_courses
```

---

# 25. Deferred but planned features

The following are intentionally postponed until the corrected domain foundation is complete.

- projected next-term planning;
- proposed-semester context;
- concurrent-course validation;
- registration load validation;
- elective-pool audit;
- concentration qualification;
- graduation-project 101-CH enforcement;
- zero-credit graduation audit;
- field-training audit;
- UEL progress layer;
- Degree Audit;
- semester validation;
- course ranking/prioritization;
- single-semester planning;
- multi-semester planning;
- what-if scenarios;
- personalization;
- actual term offering integration;
- financial-risk optimization.

---

# 26. Known unresolved items

These must not be guessed.

## 26.1 Exact additional/current Regulation-23 zero-credit set

Known:

```text
ASUx11 Societal Issues
```

Current additional items are not fully confirmed.

---

## 26.2 Exact live term offerings

The study plan does not guarantee actual opening.

Future runtime data is needed.

---

## 26.3 Full current ASU elective pool rules by slot

Some official pool information exists, but the exact current operational mapping for every Regulation-23 ASU elective slot should be verified before authoritative audit.

---

## 26.4 UEL exceptional progression

Advisor/UEL board decisions may be needed for special cases.

Do not automate exceptions without a formal rule.

---

## 26.5 Financial consequences / UEL dollar-cost timing

Known as an important product concern.

Exact trigger/timing must be formally sourced before becoming a hard rule.

Until then it may only be represented as a configurable risk/warning, not academic truth.

---

## 26.6 Course offering prediction

Do not assume a course is always Fall-only/Spring-only unless actual source data says so.

---

# 27. Golden scenarios future tests must cover

Future implementation should eventually turn these into executable tests.

## Student history

```text
failed -> passed
passed -> improvement
passed -> improvement -> failed
withdrawn
incomplete/I
currently registered
partial history
unavailable history
```

## Normal prerequisite

```text
CSE241 requires CSE141
```

## Projected prerequisite

```text
PHM111 currently in progress
plan PHM112 next term
=> conditional on PHM111 pass
```

## Concurrent prerequisite

```text
CSE392 + CSE493 in same proposed semester
=> allowed by current cohort rule
```

## Graduation gate

```text
earned CH = 100
=> graduation stage unavailable

earned CH = 101
=> earned-credit gate satisfied
```

subject to all other rules.

## Technical electives

```text
7 total
5 from Software
2 anywhere
=> concentration satisfied
```

and:

```text
7 total
4 Software
3 Data Science
=> concentration not yet satisfied
```

## Zero credit

```text
all credit-bearing requirements complete
ASUx11 not passed
=> not graduation-ready
```

## GPA load

Test all registration bands:

```text
>=3.0
2.0-<3.0
<2.0
```

including both CH and course-count dimensions.

## UEL

```text
ASU progress okay
UEL module outstanding
=> ASU eligibility may remain valid
=> UEL delay/progression warning remains
```

---

# 28. Practical rules for future Codex prompts

Every future Planning prompt should include these instructions where relevant:

1. **Inspect the real current implementation before changing semantics.**
2. **Do not infer academic rules from intuition.**
3. **Use Regulation and Program scope explicitly.**
4. **Preserve provenance.**
5. **Unknown != false.**
6. **Unsupported != ignored.**
7. **Recommended semester != offering != eligibility.**
8. **ASU progress != UEL progress.**
9. **Elective slot != course.**
10. **Current registration != passed.**
11. **Incomplete/I != in progress.**
12. **Retake/improvement must preserve attempts.**
13. **Concurrency requires proposed-semester context.**
14. **Reg18 and Reg23 must remain separate rule sets.**
15. **Do not make authoritative decisions from unresolved conflicts.**
16. **Do not stage/commit unrelated Academic Data or documentation unless explicitly requested.**
17. **Use strict RED -> GREEN -> REFACTOR for Planning implementation tasks.**

---

# 29. Current implementation roadmap

Current completed foundation:

```text
Planning Domain Foundation          DONE
Execution/Safety Policy             DONE
Provenance + Reason Codes           DONE
DecisionTrace                       DONE
Rule Expressions                    DONE
RuleEvaluator                       DONE
StudentStateBuilder v1              DONE, NEEDS v2 CORRECTION
Eligibility Engine v1               DONE, NEEDS v2 LATER
Academic Data Adapter               DONE
Real-data integration               DONE
Dependency Graph                    DONE
```

Next sequence:

```text
Task 07 — Student Academic State v2 + CourseIdentity fix
Task 08 — Registration / Eligibility v2
Task 09 — Program Requirement models
Task 10 — Degree Audit
Task 11 — Semester Validation
Task 12 — Ranking / Prioritization
Task 13 — Single-Semester Planner
Task 14 — Multi-Semester Planner
Task 15 — UEL-aware priority/risk layer
Task 16 — What-if / personalization
```

Task numbering may shift, but the dependency order should remain approximately this way.

---

# 30. Current key mental model

The final product should not be thought of as:

```text
passed courses
    ↓
find unlocked courses
    ↓
recommend five
```

It should be thought of as:

```text
                    Student Record
                         │
                         ▼
               Canonical Academic State
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        ASU Academic Rules      UEL Progress
              │                     │
              └──────────┬──────────┘
                         ▼
                 Degree / Progress Audit
                         │
                         ▼
                Candidate Course Set
                         │
                         ▼
                 Semester Validation
            ┌────────────┼─────────────┐
            │            │             │
     prerequisites     load       concurrent rules
     requirements      limits      term context
            │            │             │
            └────────────┼─────────────┘
                         ▼
                    Valid Plans
                         │
                         ▼
                   Prioritization
            ┌────────────┼─────────────┐
            │            │             │
       graduation     dependency      UEL risk
        progress       unlocks         /delay
            │            │             │
            └────────────┼─────────────┘
                         ▼
                  Recommended Plan
                         │
                         ▼
                  LLM explanation
```

The deterministic engine computes the academic truth.

The LLM explains it.

---

# 31. Final working principles

Before implementing any academic rule, ask:

1. **What exact question is the engine answering?**
2. **What source owns the answer?**
3. **Is it a hard constraint, a soft preference, or an advisor exception?**
4. **What happens if the data is missing?**
5. **Does the rule differ by Regulation?**
6. **Does it require current-semester context?**
7. **Does it belong to ASU, UEL, or both?**
8. **Can the result be explained and traced?**

If these are not clear, do not hide the uncertainty in code.

---

## Files/sources this decision record is based on

- `Bylaw 2023.pdf` — September 2023 FoE-ASU undergraduate bylaws.
- `23P - CAIE - course tree.pdf` — current Regulation-23 CAIE cohort study plan supplied by the user.
- Regulation 2018 academic material previously supplied to the project.
- UEL handbook/module/mapping material previously supplied to the project.
- Academic Data Foundation package and its normalized/conflict/review data.
- Current Planning Engine implementation through the Dependency Graph checkpoint.
- Direct clarifications supplied by a current Regulation-23 CAIE senior student.

---

**Rule for future sessions:**  
If a future design conflicts with this file, explicitly surface the conflict and ask for a decision. Do not silently replace these semantics.
