# Academic Reviewer Guide

The purpose of review is to authorize academic truth, not to check Python implementation.

## Reviewer inputs

Use `reports/academic_review_decisions_template.csv` together with the referenced source documents/pages.

For each conflict, provide:

- chosen authoritative value or corrected official value;
- authoritative source/document;
- reviewer name or institutional identifier;
- review date;
- optional explanation.

Do not approve an item merely because it is convenient for the current planner implementation.

## Critical data requiring sign-off

At minimum review:

- prerequisite and co-requisite logic;
- GPA/load restrictions;
- graduation thresholds;
- graduation-project eligibility;
- training requirements;
- elective completion/concentration rules;
- academic standing/dismissal rules;
- source authority when two supplied documents disagree;
- golden expected answers used to test the Planning Engine.

## Lifecycle

`SOURCE_VERIFIED` means the project team traced the data to the supplied source. `APPROVED` means an academic reviewer has accepted it for computational use. These must not be treated as equivalent.
