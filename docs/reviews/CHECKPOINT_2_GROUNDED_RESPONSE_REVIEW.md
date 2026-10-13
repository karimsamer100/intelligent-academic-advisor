# Checkpoint 2 — Grounded Response Reliability and Structured Academic Facts

Date: 2026-10-13
Repository: `karimsamer100/intelligent-academic-advisor`
Branch: `feat/orchestration-grounded-advisor`
Verified implementation commit: `b1bb5c7a67b21c6c4163b64d81d3c5041a6d7f47`

## Outcome

Checkpoint 2 is implemented, verified offline, committed, and pushed. The
change is additive: existing `AdvisorResponse` fields and provider-neutral
orchestration behavior remain available, while trusted structured facts are
exposed in a separate typed channel. Checkpoint 3 has not been started.

The locked authority split is preserved:

- Planning Engine and Structured Academic Data remain authorities for
  structured academic facts and deterministic decisions.
- RAG remains an official-document evidence source for policies, procedures,
  quotations, and document metadata.
- The LLM selects tools and explains returned results; it does not make
  academic decisions.

No Planning algorithm, academic dataset, RAG retrieval behavior, four-tool
registry membership, trusted student-context boundary, frontend, HTTP route,
Ollama provider, or 3-round/5-execution orchestration limit was changed.

## What changed and why

### Typed response facts

`backend/app/orchestration/facts.py` adds the typed response-facts contract and
`build_advisor_academic_facts()`:

- `AdvisorAcademicFacts` groups facts into `eligibility`,
  `course_information`, `degree_audit`, and `official_documents`.
- `AdvisorToolAuthority` records the responsible source (`PLANNING` or `RAG`),
  the exact `authoritative` value where the tool has one, the exact
  `requires_human_review` value where the tool has one, and explicit coverage
  limitations.
- `AdvisorPlanningCitation` preserves Planning source/rule/page and lifecycle
  metadata without claiming that a source/page pair semantically supports a
  generated sentence.
- `AdvisorOfficialDocumentEvidence` preserves only actual returned RAG result
  fields, including source and page range.
- `AdvisorGroundingAssessment` reports `NO_TRUSTED_FACTS`, `GROUNDED`, or
  `SAFE_FALLBACK` with deterministic issue codes.

`backend/app/orchestration/contracts.py` adds these fields to
`AdvisorResponse` with defaults:

```python
academic_facts: AdvisorAcademicFacts = Field(default_factory=AdvisorAcademicFacts)
grounding: AdvisorGroundingAssessment = Field(
    default_factory=AdvisorGroundingAssessment
)
```

The old fields remain unchanged: `text`, `tool_name`, `tool_result`,
`requires_human_review`, `tool_executions`, and `transcript`. Existing
single-tool consumers can continue using the legacy fields; multi-tool
consumers can use the execution history and facts without parsing natural
language.

### Deterministic facts construction

`build_advisor_academic_facts()` accepts already recorded tool execution
records. It includes a result only when the execution status is `executed`, the
result is structured, and it has no error payload. Failed, rejected, malformed,
or partial tool results do not become trusted academic facts. A partial turn
can retain a successful eligibility fact while omitting a failed audit fact.

The builder never inspects the generated answer. It copies exact projection
values, including `decision`, `eligible`, `authoritative`,
`requires_human_review`, coverage statuses, credits, requirement outcomes, and
provenance. It does not derive eligibility or review from authority.

### Narrow final-answer protection

`backend/app/orchestration/grounding.py` adds `protect_advisor_text()`, called
by `AdvisorOrchestrator._response()` after tool execution and before the
response is returned.

This is intentionally not a general-purpose semantic fact checker and does
not make another LLM request. It compares only directly detectable patterns
with trusted structured metadata:

- positive/negative eligibility contradiction;
- indeterminate eligibility stated as a definite answer;
- degree-audit completed/required/remaining-credit contradictions;
- degree-audit requirement-count and completion-status contradictions;
- course credit-hour contradictions;
- unavailable/incomplete prerequisite or corequisite coverage presented as a
  confirmed absence;
- no-evidence RAG results presented as a structured academic fact;
- non-authoritative Planning results presented as official approval;
- a degree-audit review flag attributed to eligibility;
- explicit source/page metadata that is unsupported or mismatched.

When a critical, deterministically detectable contradiction is found, generated
text is replaced by a compact safe summary containing trusted status/decision
values. The complete machine-readable facts remain in `academic_facts`, and
`grounding.status` is `SAFE_FALLBACK`. Otherwise the original generated text
is retained and the assessment is `GROUNDED` when trusted facts exist. A
no-tool response remains unchanged with `NO_TRUSTED_FACTS`.

Automatic semantic verification of a quotation or prose claim is not claimed.
Source/page metadata is checked where explicit metadata is present; whether a
returned text semantically supports every sentence remains future work.

## Structured response examples

### Eligibility and authority

The facts preserve this exact Planning result:

```json
{
  "decision": "ELIGIBLE",
  "eligible": true,
  "authoritative": false,
  "requires_human_review": false
}
```

`authoritative=false` is not converted into ineligibility or a formal review
flag. The legacy response `requires_human_review` remains the compatibility
aggregate across executed tool results; it does not replace per-tool facts.

### Compound eligibility plus degree audit

```text
academic_facts.eligibility[0].decision                = ELIGIBLE
academic_facts.eligibility[0].authoritative           = false
academic_facts.eligibility[0].requires_human_review   = false

academic_facts.degree_audit[0].status                 = HUMAN_REVIEW_REQUIRED
academic_facts.degree_audit[0].requires_human_review = true

response.requires_human_review                         = true  # aggregate only
```

The runtime guard rejects a directly detectable claim that eligibility itself
requires review when the eligibility result says it does not.

### CSE221 static course information

The existing structured course-information projection is copied into
`academic_facts.course_information`. The CSE221 R23/CAIE prerequisite tree
remains:

```json
{
  "type": "AND",
  "children": [
    {"type": "COURSE_PASSED", "course_code": "CSE141"},
    {"type": "COURSE_PASSED", "course_code": "CSE121"}
  ]
}
```

Nested `AND`, `OR`, and `NOT` objects remain nested. The response does not
flatten alternatives, evaluate student history, or create an eligibility
decision from static course facts. Normalized development data remains
`authoritative=false`, and typed corequisite coverage remains
`UNAVAILABLE`, not confirmed absence.

### Official document evidence

`academic_facts.official_documents` contains actual returned RAG results and an
explicit `coverage_status` of `AVAILABLE`, `NO_EVIDENCE`, or `INCOMPLETE`.
Empty RAG results cannot become a claim that a prerequisite or policy does not
exist. Planning citations and RAG evidence remain separate categories.

## Degree-audit and citation improvements

`backend/app/tools/projections.py` retains the bounded aggregate degree-audit
shape and `project_degree_audit()` now adds:

- `satisfied_ids`;
- bounded `details` with requirement ID, type, outcome,
  `requires_human_review`, reason codes, warnings, course code where present,
  and requirement-specific provenance;
- `details_truncated` to make the bound explicit.

`remaining_ids` and `review_ids`, aggregate credits, status, warnings, and
legacy aggregate citations remain compatible. Details order unsatisfied and
indeterminate requirements first, then other results, and remains capped by
the existing `_MAX_LIST_ITEMS` bound. Full traces and private student history
are not exposed. The aggregate `citations` field is retained for compatibility;
requirement-level provenance is the safe association for a specific
requirement.

Planning provenance is represented by `AdvisorPlanningCitation` and remains
attached to the eligibility, course-information, or requirement fact that
produced it. RAG evidence is represented by
`AdvisorOfficialDocumentEvidence` and can contain only metadata from actual
returned results. Runtime checks validate explicit source/page metadata, not
semantic quote support.

## Routing and prompt changes

`backend/app/orchestration/prompts/advisor.py` is now
`advisor-system-v4`. It instructs the LLM to preserve exact Planning decisions
and review flags, keep eligibility/course/audit/RAG responsibilities separate,
avoid turning unavailable coverage into verified absence, avoid presenting
non-authoritative data as official approval, and omit unsupported numeric,
requirement, rule, source, or page claims. Arabic terminology is clarified
without changing machine-readable values.

The four-tool routing contract is unchanged from Checkpoint 1:

| Intent | Authority/tool |
|---|---|
| Registration eligibility | `check_course_eligibility` |
| Static course facts/prerequisites/credits | `get_course_information` |
| Degree requirements/progress | `degree_audit` |
| Official policy/procedure/document evidence | `search_official_documents` |

Compound requests continue to support independent Planning and RAG calls. No
RAG retrieval fallback was added.

## Files changed in the implementation commit

```text
backend/app/orchestration/__init__.py
backend/app/orchestration/contracts.py
backend/app/orchestration/facts.py
backend/app/orchestration/grounding.py
backend/app/orchestration/orchestrator.py
backend/app/orchestration/prompts/advisor.py
backend/app/tools/projections.py
backend/tests/orchestration/test_application_composition.py
backend/tests/orchestration/test_grounded_response.py
backend/tests/orchestration/test_orchestrator.py
backend/tests/tools/test_projections.py
tasks/plan.md
tasks/todo.md
```

The implementation commit did not include existing unrelated working-tree
changes. The status/log update and this review are documentation-only follow-up
changes.

## Verification

### Focused and regression tests

```text
python -m pytest -q tests/tools tests/planning tests/orchestration tests/llm
606 passed, 1 skipped

python -m pytest -q ../evals/orchestration
29 passed

python -m pytest -q
705 passed, 11 skipped, 1 failed
```

The one full-local failure is pre-existing and unrelated to Checkpoint 2:

```text
tests/test_config.py::test_values_are_loaded_from_environment
Expected: /tmp/docs
Observed on Windows: \\tmp\\docs
```

The focused skip is the existing academic-data integration/fixture skip. No
test was deleted, weakened, or silently skipped for this checkpoint.

### Static checks

```text
Changed-file Ruff: passed
python -m compileall -q app tests ../evals/orchestration: passed
Scoped staged git diff --check: passed
```

Full Ruff was also executed and reports five pre-existing unrelated F401
findings in `backend/app/rag/ingestion/pipeline.py`,
`backend/app/rag/repositories/memory_repository.py`, and
`backend/tests/test_rag_integration.py`. Changed files pass Ruff independently;
no unrelated Ruff findings were modified.

### Docker, PostgreSQL, and live-model boundaries

The canonical Docker check was attempted with `docker compose ps`. It was
blocked because Docker Desktop is manually paused. The Docker/PostgreSQL suite
with `REQUIRE_DB_TESTS=1` is therefore not claimed as passed. No Ollama endpoint
was contacted and no live LLM evaluation was run.

### Git and push status

```text
Implementation commit: b1bb5c7a67b21c6c4163b64d81d3c5041a6d7f47
Push: confirmed to origin/feat/orchestration-grounded-advisor
```

The documentation/status commit is created after this report and is reported
in the final handoff. Existing unrelated changes remain in the working tree:

```text
deleted: docs/decisions/Desicions.md
modified: docs/decisions/Project_Decisions.md
untracked: docs/audits/
untracked: docs/superpowers/plans/
untracked: docs/tasks/*.md
untracked: evals/llm/results.json
```

None of these paths were staged, overwritten, committed, or pushed.

## Known limitations

- The integrated Academic Data Foundation remains normalized development data;
  `SOURCE_VERIFIED` is not treated as `APPROVED`.
- Complete typed corequisite definitions remain unavailable because the current
  artifact/adapter does not provide them.
- Failed, rejected, or malformed tool payloads are omitted from trusted facts;
  execution status remains available in the existing execution history.
- Runtime citation checks validate source/page metadata only, not semantic
  support between a returned quotation and every generated sentence.
- The safe fallback is compact and English-first; broader Arabic answer-quality
  evaluation remains outside offline deterministic tests.
- Frontend rendering, chat HTTP endpoints, and a separate deterministic
  frontend decision-card schema remain unchanged.

## Intentionally deferred to Checkpoint 3

The following were not implemented:

- full grounded final-answer validation;
- broad natural-language claim verification or an additional LLM verifier;
- degree-audit response-schema redesign beyond bounded projection fields;
- cross-tool citation/semantic support validation;
- frontend response-schema or frontend implementation changes;
- general answer-repair pipelines;
- evaluation expansion and live-model deployment/evaluation;
- academic approval workflows and normalized academic-data remediation;
- reverse dependency, semester-planning, and chat HTTP tool exposure.

Checkpoint 2 is complete and stopped for review. No Checkpoint 3 work should
begin without explicit approval.
