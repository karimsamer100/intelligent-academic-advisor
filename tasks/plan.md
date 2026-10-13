# Checkpoint 2: Grounded Response Reliability

## Scope

Add a backward-compatible, deterministic academic-facts projection to
`AdvisorResponse`; preserve per-tool authority and review semantics; improve
bounded degree-audit requirement projections; and add narrow runtime checks
that replace a final answer only when a deterministic contradiction is found.

## Checkpoints

1. Add failing contract, projection, and orchestrator tests.
2. Implement typed facts construction and bounded requirement-level fields.
3. Implement narrow final-answer assessment and update the advisor prompt.
4. Run focused/regression/Docker verification, then update project records and
   write the Checkpoint 2 review.

## Boundaries

- Do not change Planning algorithms, datasets, RAG retrieval, tool registry,
  trusted context, frontend, HTTP routes, or orchestration budgets.
- Do not implement Checkpoint 3 evaluator hardening or live-model evaluation.
- Preserve all unrelated working-tree changes.
