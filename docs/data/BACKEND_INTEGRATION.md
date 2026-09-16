# Backend Integration Guide

The backend must consume **`verified/`**, never the raw PDFs, workbook, or unapproved `normalized/` records for academic computation.

## Development vs runtime

- `normalized/` is the complete development dataset, including source-verified and blocked records.
- `reports/development_dataset.sqlite` is convenient for backend development and exploration.
- `verified/` contains only records with `approval_status = APPROVED` and no active conflict.
- `verified/runtime.sqlite` is the strict runtime SQLite export.

## PostgreSQL

Use `schemas/postgresql.sql` as the reference database structure. For production import, load `verified/source_registry.json` first, followed by:

1. `verified/courses.json`
2. `verified/prerequisites.json`
3. `verified/academic_rules.json`
4. `verified/program_requirements.json`
5. `verified/elective_pools.json`
6. `verified/uel_modules.json`
7. `verified/uel_asu_mapping.json`

Do not import a normalized record into the production Planning Engine merely because it is `SOURCE_VERIFIED` or `integration_ready`; the runtime gate is `APPROVED`.

## Suggested service boundary

The academic-data repository should expose data to the Planning Engine through repository/service functions such as:

- `get_course(course_id)`
- `get_prerequisite_rule(course_id)`
- `get_academic_rules(regulation, program, rule_type)`
- `get_program_requirements(regulation, program)`
- `get_elective_pool(pool_id)`
- `get_course_dependencies(course_id)`

The LLM should never parse these source JSON files directly to make academic decisions. The Planning Engine computes from the verified data; RAG provides textual evidence separately.
