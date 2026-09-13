# Academic Data Foundation — Final Development Package

> **Task Owner:** Academic Data / Rules  
> **Project:** Local Intelligent Academic Advisor  
> **Scope:** Regulations **2018** and **2023** + UEL mapping data  
> **Goal:** Convert the current collected academic data into a **verified, versioned, machine-readable, database-ready academic dataset** that the Planning Engine and the rest of the backend can safely depend on.

---

## 1. What this task is

This task is **not** just "finish the Excel sheet".

The final output must be a complete **Academic Data Foundation** that can be regenerated, validated, reviewed, and imported into the backend without manual copy/paste.

The final data package must contain:

- Clean normalized academic data.
- Regulation-aware course data.
- Prerequisites and co-requisites.
- Academic rules.
- Program/graduation requirements.
- Elective pools.
- UEL modules and mappings.
- Source provenance.
- Verification / approval state.
- Conflict tracking.
- Validation scripts.
- Export / import-ready files.
- Golden academic test cases.
- Clear documentation.

The system must be able to distinguish between:

1. **Official source documents** — the original truth.
2. **Structured academic data** — used for computation.
3. **RAG source metadata** — used later for retrieval/citations.

---

## 2. Current starting point

The current workbook is already a strong starting point and contains the following main assets:

- **188 courses**
  - 99 Regulation 2018
  - 89 Regulation 2023
- **165 prerequisite relations**
- **70 academic rules**
- **22 program requirements**
- **72 elective-pool rows**
- **2,397 RAG chunk-index rows**
- **30 golden test cases**
- **24 synthetic student profiles**
- **48 UEL modules**
- **73 UEL ↔ ASU mapping rows**

It also already contains useful sheets such as:

- `Document Inventory`
- `Courses Unified`
- `Prerequisite Relations`
- `RAG Sources`
- `2023 Conflicts`
- `Verification Queue`
- `Academic Rules`
- `Program Requirements`
- `Elective Pools`
- `Golden Test Cases`
- `Courses Ready`
- `Prerequisites Ready`
- `Dependency Summary`
- `Source Registry`
- `RAG Chunk Index`
- `Student Profiles`
- `Data Dictionary`
- `Quality Report`
- `UEL Modules`
- `UEL-ASU Mapping`

The next task is to turn this from a strong extraction workbook into a **development-ready academic data package**.

---

## 3. Core rule

> **Never resolve academic conflicts by guessing.**

If two official sources disagree:

- Keep both values.
- Mark the conflict.
- Identify the exact source/page.
- Ask the department / supervisor / academic reviewer which source is authoritative.
- Only then mark the final value as approved.

The Planning Engine must never depend on a guessed academic rule.

---

## 4. Required final folder structure

The final package should follow approximately this structure:

```text
data-foundation/
│
├── README.md
├── configs/
│   ├── regulations.yaml
│   ├── programs.yaml
│   ├── documents.yaml
│   └── validation.yaml
│
├── schemas/
│   ├── course.schema.json
│   ├── prerequisite.schema.json
│   ├── academic_rule.schema.json
│   ├── program_requirement.schema.json
│   ├── elective_pool.schema.json
│   ├── source.schema.json
│   ├── student_history.schema.json
│   └── golden_case.schema.json
│
├── raw/
│   └── source_inventory.csv
│
├── normalized/
│   ├── courses.csv
│   ├── prerequisites.json
│   ├── academic_rules.json
│   ├── program_requirements.json
│   ├── elective_pools.csv
│   ├── uel_modules.csv
│   ├── uel_asu_mapping.csv
│   └── source_registry.csv
│
├── verified/
│   ├── courses.json
│   ├── prerequisites.json
│   ├── academic_rules.json
│   ├── program_requirements.json
│   ├── elective_pools.json
│   └── dataset_manifest.json
│
├── rag/
│   ├── source_registry.json
│   └── chunk_manifest.json
│
├── golden_tests/
│   ├── eligibility.json
│   ├── prerequisites.json
│   ├── credit_rules.json
│   ├── graduation.json
│   ├── electives.json
│   ├── special_cases.json
│   └── conflicts_and_unsupported.json
│
├── scripts/
│   ├── extract/
│   ├── transform/
│   ├── validate/
│   └── export/
│
└── reports/
    ├── conflicts.csv
    ├── unresolved_items.csv
    ├── validation_report.json
    └── approval_report.csv
```

The exact filenames can change if needed, but the logical separation should remain.

---

## 5. Step-by-step work

### Step 1 — Clean the Source Registry

Create one clean registry for every official source document.

Each source should include at least:

```text
source_id
file_name
document_type
regulation
program
effective_year
version
official_status
relative_path
page_count
used_for_structured_data
used_for_rag
hash
notes
```

### Required rules

- Every source gets a stable `source_id`.
- Duplicate files should be identified.
- Old / superseded files should remain recorded but clearly marked.
- If the same rule appears in more than one source, preserve provenance for both.

---

## 6. Courses

Create one normalized course dataset covering **both Regulations 2018 and 2023**.

Minimum fields:

```text
course_id
regulation
program
course_code
course_name
credit_hours
ects
swl
lecture_hours
tutorial_hours
lab_hours
total_contact_hours
semester
course_type
concentration_or_track
source_id
source_page
verification_status
approval_status
notes
```

Recommended stable ID:

```text
R18:CESS:CSE111
R23:CAIE:CSE241
```

### Important

A course record should not silently mix values from different sources.

If semester/name/credits differ between sources, keep the conflict until reviewed.

---

## 7. Prerequisites and co-requisites

Do not keep prerequisites only as free-text strings such as:

```text
CSE111 AND CSE131
```

They must also have a machine-readable representation.

Example:

```json
{
  "course_id": "R18:CESS:CSE112",
  "rule_type": "PREREQUISITE",
  "expression": {
    "type": "AND",
    "conditions": [
      {
        "type": "COURSE_PASSED",
        "course_code": "CSE111"
      },
      {
        "type": "COURSE_PASSED",
        "course_code": "CSE131"
      }
    ]
  },
  "source_id": "SRC-...",
  "source_page": 9,
  "approval_status": "APPROVED"
}
```

The schema must support:

- `AND`
- `OR`
- Nested rules such as `A AND (B OR C)`
- Concurrent registration where applicable.
- Minimum credit-hour conditions.
- Minimum grade conditions if present.
- Other prerequisite types that exist in the regulations.

---

## 8. Resolve Regulation 2023 source conflicts

There are current conflicts between:

- `Bylaw 2023.pdf`
- `23P - CAIE - course tree.pdf`

Examples currently include differences related to:

- Semester.
- Course name.
- Prerequisites.

Known affected records include items such as:

```text
ASUx31
CSE241
CSE242
CSE281
CSE342
CSE381
CSE392
CSE421
CSE442
CSE481
CSE493
CSE494
EPM111
PHM132
```

### Required action

For every conflict:

1. Record both values.
2. Record both sources and pages.
3. Get the authoritative decision.
4. Record who approved the final value.
5. Record approval date.
6. Keep the old/conflicting value in conflict history.
7. Update the verified dataset only after approval.

---

## 9. Critical unresolved issue — CSE486

Current Regulation 2023 source states an incomplete prerequisite similar to:

```text
PHM113 AND ...
```

The second prerequisite is missing.

### Required action

Do **not** infer the missing course.

Obtain one of:

- Corrected official source.
- Department confirmation.
- Supervisor / academic reviewer confirmation.

Until resolved:

```text
approval_status = BLOCKED
planner_usable = false
```

---

## 10. Critical unresolved issue — CAIE technical electives

There is a current conflict between:

```text
18 CH
```

and:

```text
7 elective slots × 3 CH = 21 CH
```

### Required action

Get an authoritative answer and update all dependent places consistently:

- Program requirements.
- Elective pools.
- Graduation rules.
- Golden test cases.
- Any planner rule related to elective completion.

Do not choose 18 or 21 automatically.

---

## 11. Academic Rules — convert them to machine-readable rules

The current `Academic Rules` sheet contains useful source-derived rules, but the backend needs executable structure.

Example of an executable rule:

```json
{
  "rule_id": "R23-LOAD-001",
  "regulation": 23,
  "program": "CAIE",
  "rule_type": "MAX_CREDIT_LOAD",
  "conditions": {
    "gpa_min": 2.0,
    "gpa_max_exclusive": 3.0,
    "term_type": "MAIN"
  },
  "result": {
    "max_credit_hours": 18
  },
  "source_id": "SRC-...",
  "source_page": 42,
  "verification_status": "SOURCE_VERIFIED",
  "approval_status": "APPROVED"
}
```

### Convert all important rules that affect computation, including where available:

- Credit load limits.
- GPA-based registration rules.
- Graduation requirements.
- Earned-credit thresholds.
- Graduation project eligibility.
- Training requirements.
- Elective completion.
- Study-level progression.
- Course repetition/failure rules.
- Academic standing rules.
- Registration restrictions.
- Regulation-specific exceptions.
- Any rule required by the Planning Engine.

The goal is that the Planning Engine does not need to parse English/Arabic sentences to understand a rule.

---

## 12. Program requirements

Create machine-readable program requirements.

Each requirement should include:

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
source_id
source_page
approval_status
```

Examples:

- Core required courses.
- Faculty requirements.
- University requirements.
- Discipline requirements.
- Technical electives.
- Graduation project requirements.
- Training.
- Total program credit hours.

---

## 13. Elective pools

Create clean elective-pool definitions.

Each pool should clearly define:

```text
pool_id
regulation
program
pool_name
allowed_courses
required_number_of_courses
required_credit_hours
selection_rules
source_id
source_page
approval_status
```

Avoid storing only a text description if the rule can be represented structurally.

---

## 14. UEL data

Keep the UEL data as a separate but linked extension.

Required datasets:

```text
UEL Modules
UEL ↔ ASU Mapping
```

For each UEL module include at least:

```text
regulation
module_code
module_name
credits
level
semester_or_term
assessment_components
source
verification_status
```

For each mapping include:

```text
uel_module
asu_course_or_component
mapping_type
weight_percent
regulation
source
verification_status
```

### Validation

For every module with weighted mapping components:

```text
sum(component_weight_percent) == 100
```

If not, flag it.

---

## 15. Human academic approval state

Use an explicit lifecycle.

Recommended:

```text
EXTRACTED
SOURCE_VERIFIED
ACADEMICALLY_REVIEWED
APPROVED
BLOCKED
SUPERSEDED
```

### Important distinction

A record being:

```text
integration_ready = true
```

does **not** mean it is academically approved.

Critical academic logic must only use:

```text
approval_status = APPROVED
```

Critical data includes at least:

- Prerequisites.
- Co-requisites.
- Credit limits.
- Graduation rules.
- Graduation-project rules.
- Elective completion rules.
- Academic-standing restrictions.
- Regulation-specific restrictions.

---

## 16. Academic provenance

Every critical value or rule must be traceable to an official source.

Minimum provenance:

```text
source_id
source_file
source_page
section_if_known
extraction_method
verification_status
approved_by
approved_at
```

Example:

```json
{
  "rule_id": "R23-PR-CSE341",
  "value": "CSE231",
  "source_id": "SRC-BYLAW-2023",
  "source_page": 123,
  "approval_status": "APPROVED"
}
```

The final backend should be able to answer:

> "Why does the system think this prerequisite is CSE231?"

without searching manually through the Excel workbook.

---

## 17. Golden academic test cases

The current test cases are useful, but they need final academic review.

Create an approved golden test suite.

Each test should contain:

```text
test_id
regulation
program
category
student_state
question_or_action
expected_result
expected_reason
source_id
source_page
expected_human_review
approval_status
```

Required categories should include:

### Eligibility

```text
Student completed prerequisite → eligible.
Student missing prerequisite → not eligible.
```

### Multiple prerequisites

```text
A AND B
A OR B
nested rules if present
```

### Credit rules

```text
max load
min load
GPA-dependent load
```

### Graduation

```text
earned credits
required courses
electives
graduation project
training
```

### Special situations

```text
failed course
repeated course
blocked dependency
low GPA
high GPA
lighter load
accelerated graduation
```

### Conflict / unsupported

Questions where the correct system behavior is:

```text
requires_human_review = true
```

or:

```text
unsupported / insufficient verified data
```

### Important

Golden cases are not considered final until reviewed by someone academically qualified to validate the expected result.

---

## 18. Student history schema

The current synthetic student profiles are useful for testing, but production student history should be normalized.

Design a schema for:

```text
Student
StudentCourseAttempt
CurrentRegistration
AcademicSnapshot
```

Suggested course-attempt fields:

```text
student_id
course_id
attempt_number
term
academic_year
grade
grade_points
credits_attempted
credits_earned
status
passed
failed
withdrawn
repeated
source
```

Academic snapshot can include:

```text
gpa
earned_credit_hours
registered_credit_hours
academic_level
academic_standing
regulation
program
track
```

Do not rely on one large `completed_courses_json` field as the final database structure.

---

## 19. Validation scripts

The final data package must contain automated validation.

Minimum checks:

### Course validation

- Duplicate course IDs.
- Duplicate course codes inside the same regulation/program.
- Missing course names.
- Missing credit hours.
- Invalid semester.
- Missing regulation.
- Missing source.

### Prerequisite validation

- Prerequisite references unknown course.
- Self prerequisite.
- Duplicate prerequisite relation.
- Invalid nested expression.
- Circular dependency / cycles where not expected.
- Missing source.
- Unapproved critical relation.

### Program validation

- Requirement references unknown course.
- Elective pool references unknown course.
- Credit totals inconsistent.
- Missing required group.
- Conflicting requirement totals.

### Source validation

- Missing source ID.
- Invalid source page.
- Duplicate file hash.
- Source marked superseded but still used as current without explanation.

### Approval validation

- Critical rule not approved.
- Conflicted field marked approved without a resolution record.
- Blocked item included in verified export.

### UEL validation

- Invalid mapping.
- Weight percentages not equal to 100 where required.
- Missing module/course reference.

Example output:

```json
{
  "status": "FAILED",
  "errors": 3,
  "warnings": 12,
  "details": []
}
```

---

## 20. Conflict report

Generate a clean conflict report automatically.

Required fields:

```text
conflict_id
regulation
entity_type
entity_id
field
source_1
value_1
source_2
value_2
severity
status
resolution
resolved_by
resolved_at
```

Statuses:

```text
OPEN
IN_REVIEW
RESOLVED
BLOCKED
```

Never delete historical conflicts after resolution.

---

## 21. Configuration files

Avoid hard-coding paths and regulation information inside scripts.

Example:

```yaml
regulations:
  18:
    program: CESS
    active: true
  23:
    program: CAIE
    active: true

approval:
  critical_fields_require_human_approval: true

validation:
  fail_on_unknown_prerequisite: true
  fail_on_unapproved_critical_rule: true
  fail_on_open_conflict_in_verified_export: true
```

Document paths should also be configurable.

---

## 22. Scripts

The package should include repeatable scripts for:

### Extract

```text
Official source → extracted draft
```

### Transform

```text
Extracted draft → normalized schema
```

### Validate

```text
Normalized data → validation report
```

### Export

```text
Approved normalized data → backend/database-ready files
```

The goal is:

> If the source files change later, the data pipeline can be rerun without manually rebuilding the workbook from zero.

---

## 23. RAG-related data responsibilities

The Data Owner should prepare:

- Source registry.
- Document metadata.
- Regulation tags.
- Page mapping.
- File hashes.
- Document type.
- Effective version.
- Verification state.
- Chunk manifest if already available.

The Data Owner is **not required** to implement:

- Embedding generation.
- pgvector.
- Retrieval ranking.
- Reranking.
- LLM generation.

Those belong to the RAG Pipeline task.

The Data Owner only needs to make sure the RAG owner receives clean, reliable source metadata and official files.

---

## 24. Runtime export

Create a backend-ready export containing only data that is allowed to drive computation.

Example:

```text
verified/courses.json
verified/prerequisites.json
verified/academic_rules.json
verified/program_requirements.json
verified/elective_pools.json
```

Blocked, unresolved, and unapproved items must not silently enter the verified runtime dataset.

They remain available in:

```text
reports/unresolved_items.csv
reports/conflicts.csv
```

---

## 25. Dataset manifest / versioning

Every release of academic data should have a manifest.

Example:

```json
{
  "dataset_version": "1.0.0",
  "created_at": "2026-09-13",
  "regulations": [2018, 2023],
  "programs": ["CESS", "CAIE"],
  "source_count": 19,
  "course_count": 188,
  "approved_course_count": 0,
  "open_conflicts": 0,
  "validation_status": "PASS",
  "source_hash": "..."
}
```

Counts above are only examples in the schema; the generated manifest must use the actual final values.

Whenever a verified academic rule changes, increment the dataset version.

---

## 26. README documentation

The final Data README should explain:

- What each folder contains.
- Which sources are authoritative.
- How Regulations 2018 and 2023 are separated.
- How to run extraction.
- How to run validation.
- How to generate verified exports.
- How approval works.
- How conflicts are resolved.
- How to add a new course.
- How to add a new rule.
- How to update a source document.
- Known unresolved academic issues.
- Dataset version.

A new developer should be able to understand the data without opening the original Excel workbook first.

---

## 27. What must NOT be done

Do not:

- Guess missing prerequisites.
- Resolve source conflicts automatically.
- Mark extracted data as academically approved without review.
- Use RAG text as a computational rule.
- Store prerequisites only as human-readable strings.
- Hard-code important academic rules inside Python source code if they belong in the academic data model.
- Mix Regulation 2018 and Regulation 2023 course/rule records without an explicit regulation field.
- Delete provenance.
- Delete resolved conflict history.
- Treat `integration_ready` as equivalent to academic approval.
- Put real private student data in the repository.
- Depend on manual Excel edits as the only way to maintain the dataset.

---

## 28. Final deliverables checklist

The task is complete only when all required items below are delivered.

### Data

- [ ] Complete normalized Regulation 2018 courses.
- [ ] Complete normalized Regulation 2023 courses.
- [ ] Complete prerequisite/co-requisite structures.
- [ ] Machine-readable academic rules.
- [ ] Program requirements.
- [ ] Elective pools.
- [ ] UEL modules.
- [ ] UEL ↔ ASU mappings.
- [ ] Source registry.
- [ ] Provenance for critical rules.
- [ ] Student-history schema.

### Verification

- [ ] Regulation 2023 conflicts reviewed.
- [ ] CSE486 issue resolved or explicitly blocked.
- [ ] 18 CH vs 21 CH technical-elective issue resolved or explicitly blocked.
- [ ] Approval states added.
- [ ] Critical academic rules academically reviewed.
- [ ] Golden test cases academically reviewed.
- [ ] Unresolved issues clearly reported.

### Engineering

- [ ] JSON/CSV schemas.
- [ ] Config files.
- [ ] Extraction scripts.
- [ ] Transformation scripts.
- [ ] Validation scripts.
- [ ] Export scripts.
- [ ] Validation report.
- [ ] Conflict report.
- [ ] Dataset manifest/version.
- [ ] Backend-ready verified export.

### Documentation

- [ ] `README.md`.
- [ ] Data dictionary.
- [ ] How-to-update instructions.
- [ ] Known issues.
- [ ] Source authority notes.

---

## 29. Definition of Done

This task is considered **DONE** when another developer can do the following without manually rebuilding academic data:

```text
1. Obtain the approved official source files.
2. Run the data pipeline.
3. Produce normalized academic data.
4. Run validation.
5. See all conflicts / unresolved items.
6. Export only academically approved runtime data.
7. Run the approved golden academic tests.
8. Import the final dataset into the backend database.
```

The result should be:

```text
Official Sources
      ↓
Repeatable Extraction / Transformation
      ↓
Normalized Academic Data
      ↓
Validation + Conflict Detection
      ↓
Human Academic Approval
      ↓
Verified Versioned Dataset
      ↓
Planning Engine / Backend
```

---

## 30. Final rule for the task owner

The objective is not to make the Excel workbook look complete.

The objective is to make the academic data:

> **correct, traceable, approved, machine-readable, reproducible, testable, and safe for the Planning Engine to use.**

If an academic fact is uncertain, keep it uncertain and visible.

A clearly blocked rule is much safer than a guessed "complete" dataset.
