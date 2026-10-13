# Checkpoint 1 Implementation Review

## Structured Course Information and Planning-First Tool Routing

**Date:** 2026-10-13  
**Scope:** Approved Checkpoint 1 only  
**Status:** Implemented and verified offline; stopped for review  
**Implementation commit:** c596e7f039bba6ab3a5a7e689a64fe3a6da80d2c  
**Push:** Confirmed to origin/feat/orchestration-grounded-advisor

This checkpoint adds a read-only Planning-facing course-information tool and
routes static course questions to Structured Academic Data. It does not change
Planning algorithms, academic datasets, RAG retrieval, the bounded
Orchestrator loop, frontend contracts, or final-answer validation.

## 1. Architecture decisions and rationale

### Dedicated tool boundary

The implementation uses a dedicated get_course_information tool instead of
extending check_course_eligibility.

This preserves the distinction between:

- static course facts, including course metadata and direct rule definitions;
- student-specific eligibility and prerequisite satisfaction;
- official document wording and policy evidence.

The new tool reuses the existing Academic Data adapter and typed domain
objects. It does not instantiate a Planning Engine, use PlanningService, or
evaluate StudentState history beyond resolving the trusted regulation/program
scope required to identify a course.

### Trusted scope

The only LLM-controlled argument is course_code. The tool resolves
regulation and program through the backend-owned ToolExecutionContext and
StudentRepository, following the existing eligibility-tool boundary.

The model cannot provide or override:

- student ID;
- regulation;
- program;
- GPA;
- earned credits;
- course history;
- current registrations.

Missing trusted context uses the existing ToolContextRequiredError behavior.
Unknown or unavailable course data uses the existing safe data-unavailable
behavior.

### Authority boundary

The tool reports structured course facts. It does not create:

- an eligibility decision;
- an eligible boolean;
- a student-specific formal review flag;
- a registration recommendation.

The output retains authoritative as a data-authority signal, but it keeps
that separate from Planning decision and requires_human_review concepts. The
normalized development source returns authoritative=false. SOURCE_VERIFIED
is not treated as APPROVED.

### RAG boundary

RAG remains responsible for official policy wording, procedures, deadlines,
quotations, and document evidence. The prompt and tool descriptions now
explicitly prohibit using RAG as a fallback for structured course facts,
prerequisites, corequisites, eligibility, degree calculations, or
dependencies.

A document-focused request for exact regulation wording may still use RAG
even when it mentions a course code. Compound requests may use both Planning
and RAG when each tool addresses a separate requested responsibility.

## 2. Exact files changed

### Application implementation

- backend/app/tools/course_information.py
  - Added GetCourseInformationArguments and GetCourseInformationTool.
  - Resolves trusted scope, normalizes the course code, loads typed course and
    rule lookups, and returns the static projection.
- backend/app/tools/projections.py
  - Added project_course_information.
  - Added serialize_rule_expression for recursive typed expression trees.
  - Added bounded provenance and diagnostic projections.
- backend/app/tools/factory.py
  - Registers get_course_information as the fourth application tool.
- backend/app/tools/__init__.py
  - Exports the new tool and argument model.
- backend/app/tools/eligibility.py
  - Clarified that the existing tool is for student-specific eligibility.
- backend/app/tools/rag.py
  - Clarified that the existing tool is for policy/document evidence, not
    structured academic facts.
- backend/app/orchestration/prompts/advisor.py
  - Versioned the system prompt from advisor-system-v2 to advisor-system-v3.
  - Added explicit Planning-first routing rules while preserving valid
    multi-tool use.

### Tests and evaluation definitions

- backend/tests/tools/test_course_information_tool.py
  - Deterministic tool, scope, history-independence, expression, coverage,
    provenance, authority, validation, and serialization tests.
- backend/tests/tools/test_factory.py
  - Verifies the four-tool registry and dependency reuse.
- backend/tests/orchestration/test_application_composition.py
  - Verifies real composed CSE221 course-information routing and a
    course-facts-plus-policy batch.
- backend/tests/orchestration/test_orchestrator.py
  - Updates the prompt-version assertion.
- evals/orchestration/cases.json
  - Adds a standalone course-information case.
  - Changes eligibility_mixed to require eligibility plus
    get_course_information rather than allowing RAG as an extra tool.
  - Keeps genuine RAG-only and compound policy cases.
- evals/orchestration/evaluator.py
  - Adds the new tool's argument and result-shape contract.
- evals/orchestration/live_eval.py
  - Adds the new tool's safe argument/result reporting fields.
- evals/orchestration/test_evaluator.py
  - Tests course-information result grading and trusted-scope override
    rejection.

### Project documentation

- docs/project/PROJECT_STATUS.md
  - Records the four-tool registry, routing contract, current limitations, and
    verification evidence.
- docs/project/PROJECT_LOG.md
  - Appends the 2026-10-13 Checkpoint 1 milestone.
- docs/reviews/CHECKPOINT_1_COURSE_INFORMATION_REVIEW.md
  - This implementation report.

No normalized academic dataset, Planning algorithm, RAG retrieval module,
Orchestrator budget/validation loop, API route, frontend schema, credential,
or unrelated dirty/untracked file was changed.

## 3. Tool input and output contract

### Input

The Pydantic input model is:

~~~json
{
  "course_code": "CSE221"
}
~~~

The model is configured with extra=forbid and whitespace stripping. Any
student, scope, GPA, credit, or history field is rejected at the AcademicTool
boundary.

The backend supplies the trusted student ID separately through
ToolExecutionContext.

### Output

The projection is JSON-serializable and contains:

~~~json
{
  "course": {
    "identity": "R23:CAIE:CSE221",
    "code": "CSE221",
    "name": "Logic Design and Computer Organization",
    "credit_hours": 4,
    "regulation": "R23",
    "program": "CAIE",
    "approval_status": "SOURCE_VERIFIED",
    "verification_status": "SOURCE_VERIFIED"
  },
  "prerequisites": {
    "status": "COMPLETE",
    "rule_set_status": "COMPLETE",
    "reason_codes": [],
    "rules": [
      {
        "rule_id": "PRE-R23:CAIE:CSE221",
        "expression": {
          "type": "AND",
          "children": [
            {
              "type": "COURSE_PASSED",
              "course_id": "R23:CAIE:CSE141",
              "course_code": "CSE141"
            },
            {
              "type": "COURSE_PASSED",
              "course_id": "R23:CAIE:CSE121",
              "course_code": "CSE121"
            }
          ]
        },
        "approval_status": "SOURCE_VERIFIED",
        "verification_status": "SOURCE_VERIFIED",
        "critical_for_planner": true,
        "provenance": {
          "rule_id": "PRE-R23:CAIE:CSE221",
          "source_id": "SRC-BYLAW_2023_PDF",
          "page": 161,
          "approval_status": "SOURCE_VERIFIED",
          "verification_status": "SOURCE_VERIFIED"
        }
      }
    ],
    "expression": {
      "type": "AND",
      "children": [
        {
          "type": "COURSE_PASSED",
          "course_id": "R23:CAIE:CSE141",
          "course_code": "CSE141"
        },
        {
          "type": "COURSE_PASSED",
          "course_id": "R23:CAIE:CSE121",
          "course_code": "CSE121"
        }
      ]
    }
  },
  "corequisites": {
    "status": "UNAVAILABLE",
    "rules": [],
    "reason": "Complete typed corequisite information is not available through the Academic Data adapter.",
    "reason_codes": ["MISSING_REQUIRED_DATA"]
  },
  "coverage": {
    "course": "AVAILABLE",
    "prerequisites": "COMPLETE",
    "corequisites": "UNAVAILABLE"
  },
  "data_source": {
    "source_mode": "NORMALIZED_DEVELOPMENT",
    "dataset_version": null
  },
  "course_provenance": [],
  "authoritative": false,
  "diagnostics": []
}
~~~

The real adapter supplies the dataset version when a manifest is available.
The test projection uses a test dataset version in its fixture.

The output deliberately does not contain decision, eligible,
missing_requirements, conditions, or requires_human_review. Those belong to
student-specific eligibility or other Planning result contracts.

## 4. Preserved logical expressions

The serializer recursively handles the typed expressions currently defined by
the Planning domain:

- AND and OR retain their children and nesting.
- NOT retains an operand.
- COURSE_PASSED, COURSE_COMPLETED, COURSE_CURRENTLY_REGISTERED, and
  COURSE_CONCURRENT retain canonical course identity and course code.
- MIN_EARNED_CREDITS, MAX_EARNED_CREDITS, MIN_GPA, and MAX_GPA retain their
  numeric threshold.
- UnsupportedExpression values are returned with type UNSUPPORTED,
  source_type, supported=false, and available source metadata. They are not
  converted into executable academic rules.
- EntryRequirementExpression retains its typed reference when present.

For CSE221, the result remains:

~~~text
AND(
  COURSE_PASSED R23:CAIE:CSE141,
  COURSE_PASSED R23:CAIE:CSE121
)
~~~

The implementation does not flatten the expression into a list of mandatory
course codes and does not convert OR alternatives into AND requirements.

## 5. Unknown and incomplete coverage handling

The tool follows the current Academic Data adapter semantics:

- A missing prerequisite row is INCOMPLETE, not confirmed no-prerequisites.
- A rule-set lookup with no value is exposed as UNAVAILABLE while the
  available course metadata remains usable.
- A rule set carrying UNSUPPORTED_RULE is exposed with UNSUPPORTED coverage.
- A blocked, conflicted, superseded, or malformed rule remains represented by
  its typed rule/provenance and diagnostic state.
- Missing or empty corequisite data is never converted into confirmed
  no-corequisites. The current adapter does not expose complete typed
  corequisite definitions, so the course-information result reports
  UNAVAILABLE. If scoped adapter diagnostics identify unsupported or
  incomplete corequisite semantics, those states are preserved.
- An unknown course in the trusted regulation/program scope returns the
  existing safe ToolDataUnavailableError path.
- An invalid course-code shape returns the existing safe
  ToolArgumentValidationError path.

No academic data file was edited to add absence markers or fabricate
completeness.

## 6. Academic authority semantics

The result carries:

- course approval_status and verification_status;
- each rule's approval_status and verification_status;
- source/page/rule provenance;
- Academic Data source mode;
- dataset version when available;
- authoritative=false for the normalized development composition.

The projection only returns authoritative=true when the source mode is
VERIFIED_AUTHORITATIVE, the course is APPROVED and source-verified, the rule
set is complete, and all exposed rules are APPROVED. This is a source-data
authority signal; it is not an eligibility decision.

SOURCE_VERIFIED remains distinct from APPROVED. The tool does not turn the
current development source into institutionally approved academic data.

## 7. Planning-first routing changes

The advisor-system-v3 prompt now states:

| Intent | Tool |
|---|---|
| Static course facts, direct prerequisites, corequisites, credit hours | get_course_information |
| Can the trusted student register? | check_course_eligibility |
| Has the trusted student satisfied modeled requirements? | check_course_eligibility |
| Degree requirements and progress | degree_audit |
| Official wording, procedures, deadlines, quotations | search_official_documents |
| Course facts plus an independent policy question | Appropriate Planning tool plus RAG |

The prompt explicitly permits a document-focused question such as exact
regulation wording about a named course to use RAG. It does not ban RAG merely
because a course code appears. It does prohibit RAG from repairing or
substituting for missing structured course data.

The affected eligibility_mixed evaluation now requires:

~~~text
check_course_eligibility
get_course_information
~~~

The standalone course_information case requires only
get_course_information. The existing official_regulation RAG-only case and
compound policy cases remain available.

The existing Orchestration V2 limits and validation behavior were not changed:
maximum 3 tool rounds, maximum 5 executions, atomic batch validation,
repeated-call rejection, provider-neutral transcripts, and trusted
backend-controlled context.

## 8. Verification results

### Focused tests

Command:

~~~text
python -m pytest -q tests/tools tests/planning tests/orchestration tests/llm
~~~

Result: 588 passed, 1 skipped.

The new course-information tests passed, existing tool tests passed, real
composition tests passed, and the existing Planning/LLM/orchestration
regressions passed.

### Deterministic evaluation tests

Command:

~~~text
python -m pytest -q ../evals/orchestration/test_evaluator.py
~~~

Result: 29 passed.

### Full local backend

Command:

~~~text
python -m pytest -q
~~~

Result: 687 passed, 11 skipped, 1 failed.

The failure is the known pre-existing Windows path assertion in
tests/test_config.py, which expects /tmp/docs while the current Windows
Path representation is backslash-based. Checkpoint 1 did not modify
configuration or that test.

### Ruff

Changed-file Ruff command:

~~~text
ruff check app/tools/course_information.py app/tools/projections.py
ruff check app/tools/__init__.py app/tools/eligibility.py app/tools/factory.py
ruff check app/tools/rag.py app/orchestration/prompts/advisor.py
ruff check tests/tools/test_course_information_tool.py tests/tools/test_factory.py
ruff check tests/orchestration/test_application_composition.py
ruff check tests/orchestration/test_orchestrator.py
ruff check ../evals/orchestration/evaluator.py
ruff check ../evals/orchestration/live_eval.py
ruff check ../evals/orchestration/test_evaluator.py
~~~

Result: All checks passed.

The full app/tests Ruff command was also run. It reported five unrelated
pre-existing F401 findings in:

- app/rag/ingestion/pipeline.py;
- app/rag/repositories/memory_repository.py;
- tests/test_rag_integration.py.

Those findings were not changed.

### Compile and diff checks

compileall command:

~~~text
python -m compileall -q app ../evals/orchestration
~~~

Result: passed.

git diff --check was run. It reports the pre-existing trailing whitespace in
the already-dirty docs/decisions/Project_Decisions.md change. No application
code change introduced a reported diff-check issue.

The evaluation case JSON was parsed successfully with Python's JSON tool.

### Docker, database, and live model verification

The canonical Docker Compose full-suite command was not runnable because the
Docker Desktop Linux engine was unavailable:

~~~text
docker compose ps
failed to connect to the docker API at
npipe:////./pipe/dockerDesktopLinuxEngine
~~~

Therefore the Docker/PostgreSQL suite with REQUIRE_DB_TESTS=1 is recorded as
blocked by environment, not as passed. No Ollama endpoint was contacted and
no live LLM evaluation was run.

## 9. Known limitations after Checkpoint 1

- The current application composition uses normalized development Academic
  Data, so course facts remain non-authoritative.
- The current corequisites.json artifact is empty and the existing typed
  adapter contract does not expose complete corequisite definitions.
- The tool uses trusted student scope to resolve a bare course code. A
  future session without trusted scope must ask for clarification or use an
  explicitly approved scope-resolution policy; the model cannot supply it.
- Reverse dependency questions such as which courses CSE221 unlocks remain
  unsupported because the deterministic dependency graph is not exposed
  through the current ToolRegistry.
- Semester planning, chat HTTP endpoints, frontend response presentation, and
  final grounded answer quality remain outside this checkpoint.

## 10. Git hygiene and unrelated work

The Checkpoint 1 implementation was committed as:

~~~text
c596e7f039bba6ab3a5a7e689a64fe3a6da80d2c
feat(tools): add structured course information routing
~~~

The commit was pushed successfully to:

~~~text
origin/feat/orchestration-grounded-advisor
~~~

Only the Checkpoint 1 implementation, tests, routing prompt, and affected
evaluation definitions were included in that commit. Existing unrelated
working-tree changes were not staged or overwritten, including:

- deleted docs/decisions/Desicions.md;
- modified docs/decisions/Project_Decisions.md;
- docs/audits/PLANNING_RAG_ARCHITECTURE_AUDIT.md;
- docs/superpowers/plans/;
- the existing docs/tasks/*.md files;
- evals/llm/results.json.

The status/log updates and this report are separate documentation changes and
remain scoped to Checkpoint 1.

## 11. Intentionally deferred to Checkpoint 2

No Checkpoint 2 implementation was started. The following remain deferred:

- full grounded final-answer validation;
- degree-audit projection redesign;
- cross-tool citation validation;
- a new deterministic academic-fact presentation contract;
- frontend response-schema redesign;
- general answer repair;
- claim verification and cross-tool citation pipelines;
- broad corequisite data remediation;
- academic approval workflows;
- reverse dependency tool exposure;
- semester-planning tool exposure;
- chat HTTP endpoints;
- live Ollama evaluation.

The next action is project-owner review of this checkpoint. Do not begin
Checkpoint 2 without explicit approval.
