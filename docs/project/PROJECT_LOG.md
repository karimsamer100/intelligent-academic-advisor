# Project Log

Append-only milestone log for the Local Intelligent Academic Advisor.

Do not use this as the current-state file.
For current state, read `docs/project/PROJECT_STATUS.md`.

---

## 2026-10-07 — Local LLM phase validated

- Validated `qwen3.5:4b-q4_K_M` as a working development candidate through remote Ollama.
- Kept `qwen3.5:9b-q4_K_M` as the stronger original target; no permanent replacement decision yet.
- Live evaluation passed:
  - tool selection 13/13
  - valid tool arguments 13/13
  - structured JSON 2/2
  - semantic matches 2/2
- Validated English, Arabic, mixed Arabic/English, clarification behavior, trusted-context boundaries, context probes and thinking probes.
- Locked runtime behavior:
  - normal generation → default thinking
  - structured generation → `think=false`
  - default `LLM_NUM_CTX=8192`
- Confirmed that final tool execution → grounded answer flow is still the next phase.
- Reported full backend regression: 650 passed.
- Latest repository checkpoint after RAG test isolation:
  - `ee8c1c6fe3c96b39b81df917c68c7cbbdcc82105`
  - `test(rag): isolate pgvector scope regression`

## 2026-10-07 — Pre-orchestration hardening completed

Commit:

```text
e3a358bedf286fc6227cd7bba84ac27b44e591b2
fix: harden planning and RAG tool boundaries
```

Completed:

- RAG general-document scope semantics
- per-course corequisite coverage
- LLM-facing course-code normalization
- compact Planning tool projections
- explicit Ollama context configuration
- safe unexpected tool failures
- removal of LLM-controlled RAG language filtering
- regression coverage for the fixes

Known unresolved item kept separate:

- Regulation 2018 `R18-016` is an academic-data/sign-off issue, not a code bug.

## 2026-10-04 — FastAPI LLM lifecycle wired

Commit:

```text
e7ec4935a71767ab82ace94f53c18b3495a089cf
feat(llm): wire application LLM lifecycle
```

- FastAPI application owns one shared HTTP client.
- OllamaProvider reuses the application client.
- Client is closed cleanly on shutdown.

## 2026-10-04 — Live Ollama evaluation stabilized

Commit:

```text
9555c7a2ee13e1aa75e43df275e3b1f28fc2dff5
fix(llm): stabilize live Ollama evaluation
```

- Real model evaluation path hardened.
- Runtime/context/thinking behavior validated.

## 2026-09-28 — Live LLM evaluation harness added

Commit:

```text
9a957bff30ff424c6f592a6e8de676a14555f71b
test(llm): add live Ollama evaluation harness
```

- Added explicit non-CI live-model evaluation.
- Covered language, tool selection, structured output and runtime probes.

## 2026-09-28 — Tool composition corrected

Commit:

```text
fd6695820a4e3960ef5ac3a43855367690787ccc
refactor(tools): inject application dependencies
```

- Tool factory stopped constructing Planning/RAG internals.
- Existing application dependencies are injected.

## 2026-09-28 — Initial academic tools integrated

- `check_course_eligibility`
- `degree_audit`
- `search_official_documents`
- trusted student context boundary
- tool registry
- provider-neutral tool definitions/calls

## Earlier completed foundations

The project already completed and integrated:

- Academic Data Foundation
- Backend Foundation
- Planning Engine
- RAG Pipeline
- PostgreSQL + pgvector integration
- deterministic planning semantics and provenance
- RAG citation-ready retrieval

## 2026-10-09 — Orchestration Checkpoint 1 implemented offline

- Added the typed `AdvisorRequest` / `AdvisorResponse` application contract.
- Added a stateless `AdvisorOrchestrator` using the existing `LLMService` and
  `ToolRegistry` with zero-or-one tool execution per user turn.
- Preserved provider-neutral assistant tool-call and tool-result messages,
  trusted student context, compact tool payloads, and review/indeterminate flags.
- Added the versioned advisor system prompt and deterministic fake-provider
  coverage for no-tool, eligibility, degree-audit, official-document search,
  validation, unknown-tool, provider-failure, data-unavailable, repeated-call,
  and human-review cases.
- Verification: orchestration 11 passed; LLM/tool regression 110 passed;
  full local backend 650 passed and 10 skipped, with one pre-existing Windows
  path assertion failure in `tests/test_config.py`; compileall passed.
- The remote Ollama server was unavailable. No live orchestration evaluation or
  completion claim was made. No commit was created; this remains an uncommitted
  review checkpoint.

## 2026-10-09 — Orchestration Checkpoint 2 composition verified offline

- Added explicit application composition for the existing LLMService,
  PlanningService, Academic Data adapter, StudentRepository, request-scoped
  RAGService, ToolRegistry, and AdvisorOrchestrator.
- Reused app-owned static Planning/academic dependencies and preserved the
  existing request-scoped RAG database-session lifecycle.
- Exercised the real eligibility, degree-audit, and PostgreSQL-backed RAG tools
  with deterministic fake LLM provider responses.
- Verification: composition + orchestration 18 passed; LLM/tool regression
  110 passed; combined focused run 128 passed; Docker DB-required backend 668
  passed; compileall and Ruff passed.
- Normalized Academic Data remains explicitly non-authoritative, and
  incomplete/human-review outcomes remain in the application contract.
- Ollama was not contacted. Live final-answer evaluation remains pending.

## 2026-10-09 — Orchestration Checkpoint 2 committed and evaluation prepared

- Commit: `af7cfec990decc7400ae1395281a2ec8f41ca2af`.
- Pushed to `origin/feat/orchestration-grounded-advisor`.
- Verified composition + orchestration: 18 passed; LLM/tool regression: 110
  passed; combined focused run: 128 passed; Docker DB-required backend: 668
  passed; compileall and Ruff passed.
- Added a separate non-CI orchestration evaluation runner and deterministic
  evaluator tests; live Ollama was not contacted.
- Live grounded-response evaluation remains pending.

## 2026-10-09 — Orchestration evaluation harness committed

- Commit: `0fa4c5ec02ec4b180780241e5560b386c925ede3`.
- Pushed to `origin/feat/orchestration-grounded-advisor`.
- Verified evaluator tests: 12 passed; focused orchestration/LLM/tools: 128
  passed; Docker DB-required backend: 668 passed; compileall and Ruff passed.
- The harness remains non-CI and does not claim live Ollama evaluation.
- Live grounded-response evaluation remains pending.

## 2026-10-09 — Evaluation narrative grading hardened

- Follow-up commit: `493d384c587419b9ccd79cfce486e350883fb2ec`.
- Eligibility, degree-audit, and official-document narratives that cannot be
  verified structurally now require manual review; deterministic contradictions
  remain hard failures.
- Final offline verification: evaluator tests 13 passed; focused
  orchestration/LLM/tools 128 passed; Docker DB-required backend 668 passed;
  compileall and Ruff passed.
- Live grounded-response evaluation remains pending.

## 2026-10-09 — Orchestration evaluator hardening completed

- Citation and language grading fix: `c82f0f04d33d4519ced0cf953f932f4ef94536ee`.
- Evaluation report prompt-redaction fix: `9a91e0a5fb6f519682d3633ffb4679d47cca2a2d`.
- Verified evaluator tests: 17 passed; focused orchestration/LLM/tools: 128
  passed; Docker DB-required backend: 668 passed; compileall and Ruff passed.
- Verified the evaluator CLI import/help path offline without contacting Ollama.
- Persisted report prompts and answers are redacted; no final grounded-response
  quality approval has been granted.
- Live grounded-response evaluation remains pending.

## 2026-10-09 — Bounded multi-tool orchestration V2 verified offline

- Production commit: `b13e704697f79009d279b339aa0ba652a7d9b5ec`.
- Evaluation commit: `c9aa843330638f9b9e48981a912cc30232273f6e`.
- Added bounded multi-tool rounds with a maximum of 3 rounds and 5 total
  executions per user turn, ordered execution records, transcript correlation,
  repeated-call rejection, and aggregate human-review preservation.
- Hardened canonical RAG document-type filters and retained backend-owned
  student/regulation/program scope.
- Updated the non-CI evaluator for multi-round history, zero-evidence
  retrieval, source/page consistency, degree-audit numeric/rule checks, and
  Arabic technical-token handling. The earlier real Qwen report remains the
  baseline; no new Ollama request was made.
- Verified focused backend LLM/tools/orchestration: 146 passed; evaluator:
  27 passed; Docker DB-required backend: 686 passed; compileall and Ruff
  passed.
- Live grounded-response evaluation remains pending; no final grounded-
  response quality approval has been granted.
