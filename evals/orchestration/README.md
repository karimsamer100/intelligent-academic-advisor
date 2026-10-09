# Grounded advisor orchestration evaluation

This is a small, explicit, non-CI evaluation for the complete production
composition:

```text
Ollama -> bounded AdvisorOrchestrator -> ToolRegistry -> Planning/RAG -> final Ollama answer
```

The runner discovers a development student and supported courses from the
configured trusted data. It executes real eligibility, degree-audit, and RAG
dependencies; it does not substitute fake Planning or RAG results in live
mode. Each case receives a fresh request-scoped RAG session while the
application-owned static Planning and academic-data dependencies are reused.
The orchestrator permits at most 3 tool rounds and 5 total tool executions per
turn, and records every requested and executed call.

## Run later when Ollama is available

From the repository root, with Docker Compose and the configured database
running:

```powershell
docker compose run --rm --no-deps -w /app `
  -v "${PWD}/evals/orchestration:/evals/orchestration" `
  -e PYTHONPATH=/app `
  backend python /evals/orchestration/live_eval.py `
  --cases /evals/orchestration/cases.json
```

Run focused cases without editing the case file by repeating `--case-id`, for
example `--case-id eligibility_ar --case-id compound_grounded_advisor`.

The generated JSON is written under `evals/orchestration/results/`, which is
gitignored. The command exits `0` only for an all-PASS result, `1` for a hard
failure, `2` when live dependencies or prerequisites are unavailable, and `3`
when manual review is required.

The runner never writes academic or RAG data and does not require an HTTP chat
endpoint. It records bounded tool evidence and model answers for evaluation;
it does not include the trusted student identifier or student-specific GPA and
credit totals in the result payload.

## Cases and grading

The prepared cases cover English, Arabic, mixed-language eligibility, degree
audit, official regulation evidence, a trusted GPA/credit override attempt,
an ambiguous clarification request, a discovered human-review eligibility
case, and compound/sequential multi-tool questions. Cases whose real
prerequisites are not present are explicitly marked `SKIPPED`; no academic
result is invented.

Automated grading checks requested tools across all rounds, bounded execution,
trusted argument boundaries, deterministic Planning contradictions, human-
review preservation, numeric/rule consistency where trusted data is explicit,
and whether cited source IDs/pages occur in returned RAG evidence. A
contradiction of a deterministic Planning result is a hard failure. Retrieval
with no evidence, unsupported or ambiguous citations, and nuanced language,
completeness, and academic interpretation require manual review; a PASS is not
a claim that live academic correctness has been fully verified.

## Deterministic evaluator tests

These tests do not contact Ollama. Run them explicitly from a backend-aware
environment, for example:

```powershell
docker compose run --rm --no-deps -w /app `
  -v "${PWD}/evals/orchestration:/evals/orchestration" `
  -e PYTHONPATH=/app `
  backend python -m pytest -q /evals/orchestration/test_evaluator.py
```

The evaluator tests use fake provider-neutral responses and cover a valid
grounded answer, a Planning contradiction, unsupported citation, missing
human-review warning, unavailable tool output, and prerequisite skipping.
