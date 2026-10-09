# Project Status

**Project:** Local Intelligent Academic Advisor
**Status date:** 2026-10-09
**Repository:** `karimsamer100/intelligent-academic-advisor`
**Integration branch:** `feat/orchestration-grounded-advisor`
**Current verified code HEAD:** `9a91e0a5fb6f519682d3633ffb4679d47cca2a2d`
**Latest verified code commit:** `fix(orchestration): redact evaluation report prompts`

---

## 1. Current Phase

The core backend foundations are integrated.

```text
Academic Data Foundation      DONE / known unresolved academic items remain
Backend Foundation            DONE
Planning Engine               DONE
RAG Pipeline                  DONE
Local LLM Foundation          DONE
Real Local LLM Validation     DONE
Pre-Orchestration Hardening   DONE
Orchestration                 COMPLETE OFFLINE / LIVE EVALUATION PENDING
Final Grounded Responses      OFFLINE LOOP VERIFIED / LIVE QUALITY PENDING
Chat API / Persistence        NOT STARTED
Frontend Implementation       DESIGN IN PROGRESS
CI Workflow                   NOT IMPLEMENTED YET
```

**Immediate technical phase:** Orchestration and grounded final-answer evaluation.

---

## 2. Core Architecture

```text
Student
  ↓
Web App
  ↓
Backend / Orchestrator
  ├─ Trusted Student Context
  ├─ Planning Engine
  ├─ RAG
  └─ Local LLM
  ↓
Grounded student-facing response
```

Locked responsibility split:

- **LLM:** conversation, intent understanding, clarification, tool selection, explanation.
- **Planning Engine:** deterministic academic decisions.
- **Structured academic data:** computational academic truth.
- **RAG:** official textual evidence and citations.
- **Trusted student context:** student-specific facts.
- **Human advisor:** unresolved / exceptional cases.

The LLM must not override deterministic academic truth.

---

## 3. Current Backend / Planning / RAG State

### Backend

Implemented:

- Python + FastAPI
- PostgreSQL
- pgvector
- SQLAlchemy
- Alembic
- Docker Compose
- central typed configuration
- structured errors and logging
- health/readiness infrastructure

### Planning Engine

Implemented deterministic capabilities include:

- eligibility
- degree audit
- program progress
- semester validation
- candidate generation
- ranking
- single-semester planning
- multi-semester planning
- what-if evaluation
- UEL progress evaluation
- provenance / decision trace
- fail-closed handling for unknown academic truth

Planning scope is currently **frozen** unless a real integration need requires a change.

### RAG

Implemented:

- extraction / cleaning / chunking
- metadata
- local embeddings
- PostgreSQL + pgvector persistence
- filtered retrieval
- citation-ready results
- regulation/program scoping
- RAG scope hardening for general documents
- per-course corequisite coverage fix
- LLM-facing language filter removed

Known retrieval decisions should remain evaluation-driven; do not invent a similarity threshold without evidence.

---

## 4. Local LLM State

### Provider architecture

Implemented:

```text
caller
  ↓
LLMService
  ↓
LLMProvider
  ↓
OllamaProvider
  ↓
Ollama
  ↓
Qwen
```

FastAPI owns one shared `httpx.Client`; the provider reuses it and application shutdown closes it.

### Current validated model

Validated development candidate:

```text
qwen3.5:4b-q4_K_M
```

Validated remotely on Omar's laptop through a private network connection.

The original stronger target remains:

```text
qwen3.5:9b-q4_K_M
```

The 4B model is a validated development candidate; it has not permanently replaced 9B.

Do not commit private network addresses. Runtime endpoints belong in `.env`.

### Current runtime policy

```text
Runtime: Ollama
LLM_NUM_CTX: 8192 default
Normal generation: model default thinking
Structured generation: think=false
```

8K and 16K runtime context settings were successfully probed. Practical semantic retention was validated at roughly 4K prompt tokens; full 8K semantic retention has not been benchmarked.

### Frozen initial tool set

Exactly three initial tools:

```text
check_course_eligibility
degree_audit
search_official_documents
```

Trusted academic/student fields are server-controlled and are not accepted from the LLM as authoritative input.

Current RAG tool exposes only:

```text
query
document_types
```

Trusted regulation/program scope is injected by the backend.

### Tool hardening already completed

- course-code normalization at the tool boundary
- canonical Planning identities preserved internally
- compact LLM-facing Planning projections
- RAG general-document scope fix
- per-course corequisite coverage
- safe expected/unexpected tool-error boundary
- existing services are injected into tool composition

---

## 5. Live LLM Validation Results

Last reported live evaluation:

```text
Status:               PASS
Failures:             0
Tool selection:       13 / 13
Valid tool arguments: 13 / 13
Structured JSON:       2 / 2
Semantic matches:      2 / 2
```

Validated:

- English
- Arabic
- mixed Arabic/English
- eligibility routing
- degree-audit routing
- official-document search
- ambiguous academic requests
- out-of-scope requests
- trusted-student-data boundary
- structured JSON
- context probes
- thinking-mode probes

Important limitation:

> These tests validated understanding, tool selection, arguments, structured output, and runtime behavior. They did **not** execute the complete tool → final grounded answer loop.

### Reported performance on the validated 4B host

Tool-selection evaluation:

```text
Mean latency: ~23.13 s
Min latency:  ~15.83 s
Max latency:  ~44.65 s
```

Structured JSON:

```text
Mean latency: ~7.34 s
Min latency:  ~5.84 s
Max latency:  ~8.83 s
```

Representative generation speed:

```text
~6.7–8.3 tokens/sec
```

One transient Ollama worker crash was observed and recovered after restart. Treat this as a runtime-reliability concern to monitor, not as a proven application-code defect.

---

## 6. Regression / QA State

Last reported local regression after the LLM/RAG hardening:

```text
Full backend: 650 passed
RAG:          56 passed
LLM:          53 passed
Tools:        57 passed
Planning:     430 passed
Compileall:   passed
git diff --check: passed
```

A populated-database RAG test-isolation issue was fixed by isolating test rows with:

```text
official_status="TEST_ONLY"
```

Current repository HEAD includes that test-only fix.

Backend QA/regression work has already been carried out substantially.

Checkpoint 1 deterministic verification on 2026-10-09:

```text
Commit:                         dfb1323514baa2a5909decd86183f0af58082559
Push:                           origin/feat/orchestration-grounded-advisor
Orchestration focused tests: 11 passed
LLM + tool regression:       110 passed
Full local backend:          650 passed, 10 skipped, 1 pre-existing failure
Compileall:                  passed
```

The full local-suite failure is the existing Windows path assertion in
`tests/test_config.py`; the orchestration change does not touch configuration.
The remote Ollama server was unavailable, so no live orchestration evaluation
was run or claimed. Checkpoint 1 is complete; the later Docker-required
regression is recorded below.

Orchestration Checkpoint 2 offline composition verification on 2026-10-09:

```text
Commit:                             af7cfec990decc7400ae1395281a2ec8f41ca2af
Push:                               origin/feat/orchestration-grounded-advisor
Composition + orchestration tests: 18 passed
LLM + tool regression:             110 passed
Combined focused run:              128 passed
Docker DB-required backend:        668 passed
Compileall:                        passed
Ruff for changed Python files:     passed
```

The composed application now reuses app-owned Planning and Academic Data
dependencies, injects the request-scoped RAG service, and exercises real
eligibility, degree-audit, and RAG tools with deterministic fake providers.
Normalized development data remains non-authoritative; incomplete and
human-review outcomes remain explicit. The remote Ollama server was not
contacted, so live final-answer quality remains pending.

Live grounded-response evaluation remains pending.

Orchestration evaluation harness verification on 2026-10-09:

```text
Harness commit:                     0fa4c5ec02ec4b180780241e5560b386c925ede3
Narrative grading fix:              493d384c587419b9ccd79cfce486e350883fb2ec
Citation/language grading fix:      c82f0f04d33d4519ced0cf953f932f4ef94536ee
Report redaction fix:               9a91e0a5fb6f519682d3633ffb4679d47cca2a2d
Evaluator tests:                    17 passed
Focused orchestration/LLM/tools:   128 passed
Docker DB-required backend:        668 passed
Compileall:                        passed
Ruff for changed Python files:     passed
```

The non-CI harness uses real application composition and real Planning/RAG
dependencies when run later. It was not run against Ollama in this checkpoint.
The report persists redacted prompts and answers; original prompts are retained
only in memory for the request sent to the LLM. The runner CLI import path was
verified offline. Live grounded-response evaluation remains pending, and no
final grounded-response quality approval has been granted.

**Remaining QA infrastructure gap:** GitHub Actions CI workflow is not yet present; `.github/workflows/` currently contains only `.gitkeep`.

---

## 7. Known Academic / Product Limitations

Do not guess fixes for these.

### Regulation 2018

`R18-016` remains an academic-data / sign-off gap related to identifying the correct "Faculty requirements" membership.

This is not a Planning bug.

### Academic authority

Development data can be source-verified while still pending formal academic approval.

Never equate:

```text
SOURCE_VERIFIED == APPROVED
```

### Live term offerings

Recommended semester placement is not the same as actual term offering.

### Final advisor answers

The offline one-tool grounded response loop is implemented and deterministic
tests pass. Real Ollama final-answer quality remains unevaluated.

---

## 8. Current Team Work

### Karim / project integration

Current focus:

- Local LLM work is validated.
- Orchestration Checkpoint 2 application composition and real-tool execution
  are verified offline; real final-response evaluation remains pending until
  the Ollama host is available.
- Orchestration implementation checkpoint:
  `user → LLM → tool execution → Planning/RAG → tool result → final grounded LLM response`.
- After the Ollama host is available, run full final-response evaluation.

### Youssef

Current focus:

- frontend/product page design
- visual system and page flows are being reviewed with Karim
- implementation should continue against stable frontend contracts/mocks until backend chat contracts are ready

### CI task

A team member is assigned the backend CI workflow task.

Target:

- GitHub Actions
- Python 3.12
- PostgreSQL + pgvector
- Alembic
- `REQUIRE_DB_TESTS=1`
- full existing backend regression suite

### Omar

Omar's laptop is currently being used as the remote Ollama/model host.

Previous backend QA/regression testing has already been performed; do not assign duplicate QA work without checking what is already complete.

---

## 9. Immediate Next Technical Step

Run the smallest orchestration loop against the configured Ollama model when
the remote host is available:

```text
User
  ↓
LLM selects one of the approved tools
  ↓
Tool executes with trusted context
  ↓
Planning/RAG returns structured result
  ↓
Result is returned to the LLM
  ↓
LLM produces a grounded final answer
```

Then evaluate:

- Planning decision preserved exactly
- `INDETERMINATE` never silently becomes yes/no
- `requires_human_review` preserved
- missing prerequisites explained correctly
- RAG evidence/citations used correctly
- no invented academic facts
- English / Arabic / mixed final answer quality
- tool-error behavior
- latency

Do not expand the tool set automatically before this flow is proven.

---

## 10. Deferred High-Value Enhancements

Keep these for enhancement planning after the core end-to-end advisor flow works:

- **Computed / Cited / Escalated** answer principle
- deterministic decision cards from Planning results
- one-click Planning provenance → exact official evidence
- plain-RAG-vs-engine baseline evaluation
- "why not / how do I get there?" unlock paths
- critical-path / bottleneck analysis
- advisor escalation packets
- claim/faithfulness guard
- Arabic / mixed-language / Arabizi evaluation
- evaluation/regression dashboard

Do not start these merely because they sound impressive; prioritize the end-to-end advisor flow first.

---

## 11. Current Rule for New Work

Before starting a new task:

1. Read `docs/project/README.md`.
2. Read this file.
3. Read `docs/decisions/Project_Decisions.md`.
4. Read component-specific decision docs if relevant.
5. Inspect the current branch and exact code.
6. Do not rely on old roadmaps when current code/status says otherwise.
