# Project Reference — Start Here

This directory is the canonical entry point for understanding the **current state** of the Local Intelligent Academic Advisor.

## Read order for any new AI/chat/developer

1. `docs/project/PROJECT_STATUS.md`
2. `docs/decisions/Project_Decisions.md`
3. `docs/project/PROJECT_LOG.md`
4. Component-specific decision docs only when relevant, especially:
   - `docs/planning/Planning_Domain_Semantics_Decisions_v2.md`
   - current task/design documents under `docs/tasks/` and `docs/superpowers/specs/`
5. Inspect the current Git branch/commit and real code before changing anything.

## Source priority

When information conflicts, use this order:

1. Current repository code + current commit
2. Current approved project decisions
3. Component-specific locked decision documents
4. `PROJECT_STATUS.md` for current phase/team/runtime state
5. `PROJECT_LOG.md` for history
6. Old task briefs / old master-context documents

Old documents may describe an earlier phase. Do not treat an old roadmap as current status.

## Update rule

Update `PROJECT_STATUS.md` whenever any of these changes:

- a phase starts or finishes;
- a major component becomes integrated;
- a model/runtime decision changes;
- important evaluation metrics are produced;
- a known blocker is resolved or discovered;
- active team assignments change;
- the current next step changes.

Append to `PROJECT_LOG.md` after each meaningful milestone or architectural decision.

Update `docs/decisions/Project_Decisions.md` only when a project-wide decision changes.

Do not add routine commits or tiny fixes to the log unless they materially change project state.

## Security rule

Do not commit:

- passwords or tokens;
- `.env` values that are machine-specific;
- private IP addresses / Tailscale addresses;
- personal credentials;
- private student data.

Runtime connection details belong in local environment configuration, not in these reference files.

## AI working rule

Before implementing anything substantial:

> Read the current project reference first, inspect the real code, and surface conflicts instead of inventing missing decisions.
