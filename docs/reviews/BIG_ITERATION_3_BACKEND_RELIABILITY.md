# Big Iteration 3 - Backend Reliability Review

**Project:** Local Intelligent Academic Advisor
**Repository:** `karimsamer100/intelligent-academic-advisor`
**Branch:** `feat/orchestration-grounded-advisor`
**Review date:** 2026-10-13
**Starting HEAD:** `6511c7c6e1144cbefd13e9c8c2c2ac3527bfd1a2`
**Implementation commit:** `a326bbed827e296725fc5893bb64002e6e6f6d1b`
**Push:** confirmed to `origin/feat/orchestration-grounded-advisor`

## 1. Outcome

Big Iteration 3 is implemented and verified offline. The work keeps the
approved four-tool architecture, trusted backend student context, Planning/RAG
responsibility split, and bounded Orchestration V2 limits. It improves the
narrow runtime grounding guard, hardens the offline evaluator, and adds a real
application-composition scenario suite using deterministic providers.

The backend is ready for the next live-Qwen preparation step, subject to the
limitations in this report. No Ollama request, cloud deployment, or live model
evaluation was performed.

The next iteration is intentionally deferred: cloud-hosted Qwen inference,
latency/quality benchmarking, and live academic-answer validation.

## 2. Architecture and contract decisions

The runtime flow remains:

```text
Student question
  -> AdvisorRequest
  -> AdvisorOrchestrator
  -> LLMService / provider-neutral generation
  -> bounded ToolRegistry calls
       |-> Planning tools -> trusted student context + PlanningService /
       |                    Academic Data adapter
       |-> RAG tool       -> request-scoped RAG service + official documents
  -> ordered AdvisorToolExecution records and transcript
  -> final provider generation
  -> deterministic protect_advisor_text()
  -> AdvisorResponse
       |-> generated explanation (text)
       |-> trusted academic_facts
       |-> grounding status/issues
       |-> tool executions/transcript for diagnostics
```

Planning remains authoritative for structured course facts, eligibility,
degree audit, progress, and requirements. RAG remains an official-document
evidence source. The model selects tools and explains results; it does not
decide academic facts.

No new `AdvisorResponse` fields were required in this iteration. The existing
Checkpoint 2 additive fields are now consumed and evaluated more rigorously:

- `academic_facts` is built from successful trusted tool projections only.
- `grounding` records `NO_TRUSTED_FACTS`, `GROUNDED`, or `SAFE_FALLBACK` plus
  narrow issue codes.
- `tool_executions` and `transcript` remain available for provider-neutral
  diagnostics and are not required by a frontend to discover the core facts.

The advisor prompt is now `advisor-system-v5` in
`backend/app/orchestration/prompts/advisor.py`. It reinforces exact
AND/OR/NOT/threshold/unsupported expression handling, unavailable coverage,
source verification versus approval, and the boundary between RAG evidence
and structured academic facts.

The persisted live-evaluation report schema is now
`orchestration-live-eval-v3`. This is an evaluator/reporting change, not a
runtime tool or academic-data change.

## 3. Issues found and fixed

### 3.1 Grounding false positives

The previous authority check searched for words such as `authoritative` and
`officially approved` without reliably determining whether they were asserted.
Legitimate explanations such as “this decision is not authoritative” could
therefore produce a false `SAFE_FALLBACK`.

`backend/app/orchestration/grounding.py` now uses deliberately narrow helpers:

- `_sentence_chunks()` limits checks to short statement-like units.
- `_non_assertive_sentence()` ignores questions, quoted/metalinguistic
  wording, and common English/Arabic interrogative starts, including questions
  without a trailing question mark.
- `_negates_claim()` handles short English and Arabic negation around the
  matched claim and explicit false/no forms.
- `_claim_applies_to_course()` prevents a claim about one course from being
  attributed to another course in a multi-course answer.
- `_has_asserted_claim()` is shared by eligibility, coverage, and authority
  checks.

The guard now avoids rejecting examples such as:

- “This decision is not authoritative.”
- “The rule has not been officially approved.”
- “Is this result authoritative?”
- “What is authoritative for CSE221”
- Arabic or mixed-language cautious statements that explicitly preserve an
  ineligible/unknown/unauthoritative limitation.

The guard still detects direct, high-confidence contradictions such as an
`ELIGIBLE` Planning result being stated as “not eligible,” an unavailable
corequisite being stated as absent, a non-authoritative fact being stated as
official approval, or a trusted number being replaced by a different number.
This remains a bounded surface validator, not unrestricted semantic
verification.

### 3.2 Review-flag and cross-tool attribution

`_review_attribution_issues()` now requires an asserted eligibility-review
claim and ignores negated/cautious forms. A degree-audit review flag is not
treated as an eligibility review flag.

`_fact_citation_issues()` and `_course_fact_citation_issues()` keep explicit
Planning source/page pairs attached to the corresponding course fact. Existing
requirement-level citation checks remain in place. These checks validate
metadata mapping; they do not prove that quoted prose semantically supports a
claim.

### 3.3 Safe fallback

`_safe_facts_summary()` continues to use only structured facts. It never parses
the generated answer to create facts, derives approval from authority, or
derives a human-review flag from non-authoritativeness. When the source answer
is predominantly Arabic, `_safe_facts_summary_arabic()` provides a readable
Arabic summary while preserving the exact Planning decision, authority value,
review value, and coverage state.

Fallback does not call the provider again. It preserves the trusted facts in
`AdvisorResponse.academic_facts` and replaces only the unsafe generated text.

### 3.4 Evaluation round accounting

The evaluator previously risked counting every provider response as a tool
round, including the final provider generation that requested no tools.

`evals/orchestration/evaluator.py::_requested_rounds()` and
`evals/orchestration/live_eval.py::_tool_calls_by_round()` now count only
provider generations containing one or more tool calls. The report separately
records `provider_generation_count`, `provider_call_count`, per-call latency,
and whether the final request had no tools.

This preserves accurate accounting for both same-round multi-tool calls and
sequential tool rounds while keeping the existing maximum of three tool rounds
and five tool executions.

## 4. Evaluation V3 methodology

`evals/orchestration/evaluator.py` now reports separate dimensions instead of
collapsing all behavior into one PASS:

| Dimension | What is checked |
|---|---|
| `tool_selection_correct` | Required tools are requested and unjustified extras are not treated as success. |
| `tool_execution_success` | Required results execute and are available. |
| `trusted_arguments_integrity` | Forbidden student/scope fields are rejected and configured course arguments match. |
| `facts_integrity` | `academic_facts` exactly matches facts rebuilt from successful tool executions. |
| `tool_authority_review_integrity` | Per-tool authority and review semantics survive without cross-tool substitution. |
| `grounding_protection` | Runtime protection is classified as applied, escaped, false-positive, or not needed. |
| `narrative_quality` | Structural consistency is distinguished from a manual-review or protected model error. |
| `citation_metadata_integrity` | Returned source/page metadata and requirement mappings are checked. |
| `language_match` | Expected English/Arabic response language is recorded separately. |
| Provider/orchestration | Provider failures, generation counts, tool rounds, executions, bounds, and latency are retained. |

The evaluator explicitly distinguishes these cases:

- A model contradiction protected by `SAFE_FALLBACK` is a model mistake with
  successful runtime protection, not a narrative PASS.
- A model contradiction that reaches a `GROUNDED` response is a hard failure.
- A correct-looking model answer that is rejected is reported as a runtime
  false positive and requires manual review.
- A structurally consistent answer is marked as unverified narrative quality;
  deterministic checks do not prove unrestricted semantic correctness.
- A missing or unavailable academic result is not converted to a PASS or to a
  claim that the academic requirement is absent.

`evals/orchestration/live_eval.py` persists bounded summaries of decisions,
course coverage, progress/requirement aggregates, per-tool authority/review,
grounding issues, citations, and provider timing. It does not persist the
trusted student identifier, raw student history, or GPA. Existing prompt and
answer redaction remains in force. Course/document evidence is bounded and
intended for diagnosis, not as a replacement for application response
contracts.

The evaluator CLI help path was verified from the repository root with the
project's backend-aware `PYTHONPATH`. No live provider was contacted.

## 5. Offline end-to-end coverage

`backend/tests/orchestration/test_offline_end_to_end.py` uses the real
`build_advisor_application()` composition, application-owned Planning and
Academic Data dependencies, request-scoped RAG service, ToolRegistry, and
AdvisorOrchestrator. Only the provider and RAG retriever are deterministic
test doubles.

The nine scenarios cover:

- real CSE221 static course information, scoped identity, preserved `AND`
  prerequisite expression, and unavailable corequisites;
- eligibility plus course information in one multi-tool round, with separate
  authority/review semantics;
- real degree-audit progress and bounded requirement-level review facts;
- empty RAG retrieval represented as `NO_EVIDENCE`, not as absence of an
  academic prerequisite;
- eligibility + degree audit + RAG with independent review boundaries;
- sequential eligibility and course-information rounds;
- partial RAG failure with the successful Planning fact retained;
- provider failure with no fabricated academic facts;
- rejected attempts to override trusted student/scope context through tool
  arguments.

Existing Planning, tool, RAG-interface, orchestration, and evaluator tests
continue to cover ineligible/indeterminate decisions, human review,
unapproved/incomplete rules, nested expressions, citations, invalid codes,
repeated calls, execution bounds, and provider-neutral transcripts. The
scripted-provider suite proves backend handling of predefined model behavior;
it does not prove that Qwen will select the same tools in live inference.

## 6. Grounding and fact examples

For a successful eligibility tool result:

```text
academic_facts.eligibility[0].decision              = ELIGIBLE
academic_facts.eligibility[0].authoritative         = false
academic_facts.eligibility[0].requires_human_review = false
```

For the same turn's degree audit, the audit can independently have
`requires_human_review=true`. The combined response may therefore require
attention, but the eligibility fact remains `requires_human_review=false`.

For a compound Planning + RAG turn:

```text
eligibility       -> decision, authority, review, rule/provenance facts
course information -> static metadata, prerequisite expression, coverage
degree audit       -> progress, requirement outcomes, requirement provenance
RAG                -> returned document evidence and coverage status only
```

No result from one channel is substituted for another. In particular, empty
RAG retrieval cannot establish that a structured prerequisite does not exist,
and `SOURCE_VERIFIED` or normalized development data is not upgraded to
institutional approval.

## 7. Verification results

All commands below were executed locally against the post-fix implementation.

| Verification | Result |
|---|---:|
| Grounding tests (`test_grounded_response.py`) | 23 passed |
| Real-composition offline scenarios | 9 passed |
| Evaluator tests (`evals/orchestration/test_evaluator.py`) | 36 passed |
| Combined grounding/offline/evaluator subset | 68 passed; 2 warnings |
| Focused backend tools/planning/orchestration/LLM + evaluator | 660 passed, 1 skipped, 1 warning |
| Full local backend suite | 723 passed, 11 skipped, 1 pre-existing failure |
| Changed-file Ruff | passed |
| Full Ruff | 5 unrelated pre-existing F401 findings only |
| `python -m compileall -q app tests ../evals/orchestration` | passed |
| Scoped `git diff --check` | passed |
| Docker/PostgreSQL with `REQUIRE_DB_TESTS=1` | blocked |
| Ollama/live Qwen evaluation | not run by scope |

The full local failure is the pre-existing Windows path assertion:
`tests/test_config.py::test_values_are_loaded_from_environment` expects
`/tmp/docs`, while the Windows runtime observes `\\tmp\\docs`. No Iteration 3
change touches configuration.

Full Ruff retains these unrelated pre-existing unused imports:

- `backend/app/rag/ingestion/pipeline.py` (`json`)
- `backend/app/rag/repositories/memory_repository.py` (`RetrievalFilters`)
- `backend/tests/test_rag_integration.py` (`get_retriever`,
  `DocumentSearchService`, `PgVectorRetriever`)

Docker verification was attempted with the existing Compose setup and
`REQUIRE_DB_TESTS=1`, but Docker Desktop reported that it was manually paused.
The database suite is therefore not claimed as passed.

## 8. Known limitations and risks

- The grounding guard is intentionally narrow. It catches stable,
  deterministically comparable claims but cannot prove arbitrary semantic
  equivalence, quote support, or multilingual nuance.
- Citation checks verify source/page metadata and requirement/fact mapping;
  they do not semantically verify that a quotation supports the academic
  statement.
- Normalized development academic data remains non-authoritative. The
  existing typed corequisite coverage limitation remains explicit.
- Reverse dependencies, semester planning exposure, broad corequisite data
  remediation, approval workflows, frontend response redesign, HTTP chat
  routes, and general claim-repair pipelines remain out of scope.
- The evaluator's scripted providers test application behavior for predefined
  calls. Only a live Qwen run can measure real tool selection, language
  quality, latency, and final-answer behavior.
- Docker/PostgreSQL regression is unverified in this environment because the
  Docker engine is paused.

## 9. Files changed

Implementation commit `a326bbed827e296725fc5893bb64002e6e6f6d1b` changed only:

- `backend/app/orchestration/grounding.py`
- `backend/app/orchestration/prompts/advisor.py`
- `backend/tests/orchestration/test_grounded_response.py`
- `backend/tests/orchestration/test_offline_end_to_end.py`
- `backend/tests/orchestration/test_orchestrator.py`
- `evals/orchestration/README.md`
- `evals/orchestration/cases.json`
- `evals/orchestration/evaluator.py`
- `evals/orchestration/live_eval.py`
- `evals/orchestration/test_evaluator.py`

No Planning algorithm, structured academic dataset, RAG retrieval/index,
ToolRegistry responsibility, trusted-context boundary, orchestration budget,
Ollama provider, frontend, or HTTP route was changed.

The follow-up documentation files are:

- `docs/reviews/BIG_ITERATION_3_BACKEND_RELIABILITY.md`
- `docs/project/PROJECT_STATUS.md`
- `docs/project/PROJECT_LOG.md`

Unrelated existing dirty/untracked paths were preserved and were not staged:
the dirty decision-document changes, `docs/audits/`, `docs/superpowers/plans/`,
the existing untracked task documents, and `evals/llm/results.json`.

## 10. Readiness for next live Qwen iteration

The backend is suitable for a controlled next-iteration live evaluation:

- all four tools remain registered and provider-neutral;
- trusted scope and student context remain backend-controlled;
- structured facts are available independently from generated prose;
- grounding status and fallback reasons are persisted;
- provider generations, tool rounds, executions, and latency are separately
  measurable;
- evaluator cases cover all four tools and compound responsibilities;
- the evaluator CLI and offline real composition are usable without Ollama.

Before interpreting live results, the project owner should remember that the
current academic dataset is development/non-authoritative, corequisite facts
may be unavailable, and a scripted-provider PASS is not evidence that Qwen
will route correctly. Live evaluation must grade tool routing, argument
integrity, facts, narrative, language, citations, fallback frequency, and
latency separately.

## 11. Intentionally deferred work

Checkpoint 3 and the next live iteration remain deferred. Specifically, this
iteration did not implement:

- Modal/cloud GPU hosting or Qwen deployment;
- live Ollama/Qwen inference or benchmark measurements;
- unrestricted semantic fact checking;
- additional LLM verification calls;
- a frontend or HTTP response-schema redesign;
- new Planning tools for reverse dependencies or semester planning;
- academic-data remediation or approval workflows;
- RAG indexing, chunking, embedding, or retrieval changes.

The work stops here for review as requested.
