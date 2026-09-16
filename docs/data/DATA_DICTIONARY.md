# Data Dictionary

Generated from the repository JSON Schemas. `required = true` means the field is required by the schema.

## courses

| Field | Required | Type | Enum / notes |
|---|---:|---|---|
| `course_id` | yes | `string` |  |
| `regulation` | yes | `integer` | [2018, 2023] |
| `program` | yes | `string` |  |
| `course_code` | yes | `string` |  |
| `course_name` | yes | `string` |  |
| `credit_hours` | yes | `number` |  |
| `ects` | no | `number|null` |  |
| `swl` | no | `number|null` |  |
| `lecture_hours` | no | `number|null` |  |
| `tutorial_hours` | no | `number|null` |  |
| `lab_hours` | no | `number|null` |  |
| `total_contact_hours` | no | `number|null` |  |
| `semester` | no | `integer|null` |  |
| `course_type` | no | `string|null` |  |
| `concentration_or_track` | no | `string|null` |  |
| `source_id` | yes | `string` |  |
| `source_file` | no | `string` |  |
| `source_page` | no | `integer|string|null` |  |
| `section_if_known` | no | `string|null` |  |
| `extraction_method` | no | `string` |  |
| `verification_status` | no | `string` |  |
| `approval_status` | yes | `string` | ["EXTRACTED", "SOURCE_VERIFIED", "ACADEMICALLY_REVIEWED", "APPROVED", "BLOCKED", "SUPERSEDED", "PENDING_ACADEMIC_REVIEW"] |
| `approved_by` | no | `string|null` |  |
| `approved_at` | no | `string|null` |  |
| `conflict_ids` | no | `array` |  |
| `planner_usable` | no | `boolean` |  |
## prerequisites

| Field | Required | Type | Enum / notes |
|---|---:|---|---|
| `prerequisite_rule_id` | yes | `string` |  |
| `course_id` | yes | `string` |  |
| `regulation` | yes | `integer` | [2018, 2023] |
| `program` | yes | `string` |  |
| `rule_type` | yes | `string` | ["PREREQUISITE", "CONDITIONAL_PREREQUISITE", "ENTRY_REQUIREMENT", "COREQUISITE"] |
| `expression` | yes | `#/$defs/expression` |  |
| `source_id` | yes | `string` |  |
| `source_file` | no | `string` |  |
| `source_page` | no | `integer|string|null` |  |
| `section_if_known` | no | `string|null` |  |
| `extraction_method` | no | `string` |  |
| `verification_status` | no | `string` |  |
| `approval_status` | yes | `string` | ["EXTRACTED", "SOURCE_VERIFIED", "ACADEMICALLY_REVIEWED", "APPROVED", "BLOCKED", "SUPERSEDED", "PENDING_ACADEMIC_REVIEW"] |
| `approved_by` | no | `string|null` |  |
| `approved_at` | no | `string|null` |  |
| `conflict_ids` | no | `array` |  |
| `planner_usable` | no | `boolean` |  |
## academic_rules

| Field | Required | Type | Enum / notes |
|---|---:|---|---|
| `rule_id` | yes | `string` |  |
| `regulation` | yes | `integer` | [2018, 2023] |
| `program` | yes | `string` |  |
| `rule_type` | yes | `string` |  |
| `conditions` | yes | `object` |  |
| `result` | yes | `object` |  |
| `source_id` | yes | `string` |  |
| `source_file` | no | `string` |  |
| `source_page` | no | `integer|string|null` |  |
| `section_if_known` | no | `string|null` |  |
| `extraction_method` | no | `string` |  |
| `verification_status` | no | `string` |  |
| `approval_status` | yes | `string` | ["EXTRACTED", "SOURCE_VERIFIED", "ACADEMICALLY_REVIEWED", "APPROVED", "BLOCKED", "SUPERSEDED", "PENDING_ACADEMIC_REVIEW"] |
| `approved_by` | no | `string|null` |  |
| `approved_at` | no | `string|null` |  |
| `critical_for_planner` | no | `boolean` |  |
| `planner_usable` | no | `boolean` |  |
## program_requirements

| Field | Required | Type | Enum / notes |
|---|---:|---|---|
| `requirement_id` | yes | `string` |  |
| `regulation` | yes | `integer` | [2018, 2023] |
| `program` | yes | `string` |  |
| `requirement_type` | yes | `string` |  |
| `requirement_group` | yes | `string` |  |
| `required_courses` | no | `array` |  |
| `required_credit_hours` | no | `number|null` |  |
| `min_courses` | no | `number|null` |  |
| `max_courses` | no | `number|null` |  |
| `elective_pool_id` | no | `string|null` |  |
| `conditions` | no | `object` |  |
| `source_id` | yes | `string` |  |
| `source_file` | no | `string` |  |
| `source_page` | no | `integer|string|null` |  |
| `section_if_known` | no | `string|null` |  |
| `extraction_method` | no | `string` |  |
| `verification_status` | no | `string` |  |
| `approval_status` | yes | `string` | ["EXTRACTED", "SOURCE_VERIFIED", "ACADEMICALLY_REVIEWED", "APPROVED", "BLOCKED", "SUPERSEDED", "PENDING_ACADEMIC_REVIEW"] |
| `approved_by` | no | `string|null` |  |
| `approved_at` | no | `string|null` |  |
| `planner_usable` | no | `boolean` |  |
## elective_pools

| Field | Required | Type | Enum / notes |
|---|---:|---|---|
| `pool_id` | yes | `string` |  |
| `regulation` | yes | `integer` | [2018, 2023] |
| `program` | yes | `string` |  |
| `pool_name` | yes | `string` |  |
| `pool_type` | no | `string` |  |
| `allowed_courses` | no | `array` |  |
| `allowed_course_codes` | yes | `array` |  |
| `required_number_of_courses` | no | `integer|null` |  |
| `required_credit_hours` | no | `number|null` |  |
| `selection_rules` | no | `object` |  |
| `source_id` | yes | `string` |  |
| `approval_status` | yes | `string` | ["EXTRACTED", "SOURCE_VERIFIED", "ACADEMICALLY_REVIEWED", "APPROVED", "BLOCKED", "SUPERSEDED", "PENDING_ACADEMIC_REVIEW"] |
## sources

| Field | Required | Type | Enum / notes |
|---|---:|---|---|
| `source_id` | yes | `string` |  |
| `file_name` | yes | `string` |  |
| `document_type` | yes | `string|null` |  |
| `regulations` | no | `array` |  |
| `programs` | no | `array` |  |
| `effective_year` | no | `integer|null` |  |
| `version` | no | `string|null` |  |
| `official_status` | yes | `string` |  |
| `relative_path` | yes | `string` |  |
| `page_count` | no | `integer|null` |  |
| `used_for_structured_data` | no | `boolean` |  |
| `used_for_rag` | no | `boolean` |  |
| `sha256` | yes | `string` |  |
| `notes` | no | `string|null` |  |
| `authority_level` | no | `string|null` |  |
| `authority_precedence` | no | `string|null` |  |
| `original_relative_path` | no | `string|null` |  |
| `size_bytes` | no | `integer|null` |  |
| `rag_ingest_recommended` | no | `boolean` |  |
| `classification` | no | `string|null` |  |
| `project_role` | no | `string|null` |  |
| `project_priority` | no | `integer|number|null` |  |
| `duplicate_or_superseded_by` | no | `string|null` |  |
## golden_cases

| Field | Required | Type | Enum / notes |
|---|---:|---|---|
| `test_id` | yes | `string` |  |
| `regulation` | yes | `integer` | [2018, 2023] |
| `program` | yes | `string` |  |
| `category` | yes | `string` |  |
| `student_state` | yes | `object` |  |
| `question_or_action` | yes | `string` |  |
| `expected_result` | yes | `object` |  |
| `expected_reason` | yes | `string` |  |
| `source_id` | yes | `string` |  |
| `source_page` | no | `` |  |
| `expected_human_review` | no | `boolean` |  |
| `approval_status` | yes | `string` | ["EXTRACTED", "SOURCE_VERIFIED", "ACADEMICALLY_REVIEWED", "APPROVED", "BLOCKED", "SUPERSEDED", "PENDING_ACADEMIC_REVIEW"] |
## uel_modules

| Field | Required | Type | Enum / notes |
|---|---:|---|---|
| `uel_module_id` | yes | `string` |  |
| `regulation` | yes | `integer` | [2018, 2023] |
| `module_code` | yes | `string` |  |
| `module_name` | yes | `string` |  |
| `credits` | yes | `number` |  |
| `level` | yes | `integer` |  |
| `semester_or_term` | no | `string|integer|null` |  |
| `assessment_components` | yes | `array` |  |
| `source_id` | yes | `string` |  |
| `approval_status` | yes | `string` | ["EXTRACTED", "SOURCE_VERIFIED", "ACADEMICALLY_REVIEWED", "APPROVED", "BLOCKED", "SUPERSEDED", "PENDING_ACADEMIC_REVIEW"] |
## uel_asu_mapping

| Field | Required | Type | Enum / notes |
|---|---:|---|---|
| `mapping_id` | yes | `string` |  |
| `regulation` | yes | `integer` | [2018, 2023] |
| `uel_module_id` | yes | `string` |  |
| `asu_course_id` | yes | `string` |  |
| `mapping_type` | yes | `string` |  |
| `weight_percent` | yes | `number` |  |
| `source_id` | yes | `string` |  |
| `approval_status` | yes | `string` | ["EXTRACTED", "SOURCE_VERIFIED", "ACADEMICALLY_REVIEWED", "APPROVED", "BLOCKED", "SUPERSEDED", "PENDING_ACADEMIC_REVIEW"] |
