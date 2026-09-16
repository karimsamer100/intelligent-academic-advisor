-- PostgreSQL-oriented schema for importing the verified Academic Data Foundation.
-- JSONB is used for rule/expression payloads so the Planning Engine can evolve without schema churn.
CREATE TABLE IF NOT EXISTS academic_sources (
  source_id TEXT PRIMARY KEY,
  file_name TEXT NOT NULL,
  document_type TEXT,
  effective_year INTEGER,
  version TEXT,
  official_status TEXT NOT NULL,
  authority_level TEXT,
  authority_precedence TEXT,
  relative_path TEXT NOT NULL,
  page_count INTEGER,
  sha256 TEXT NOT NULL UNIQUE,
  used_for_structured_data BOOLEAN NOT NULL DEFAULT FALSE,
  used_for_rag BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS courses (
  course_id TEXT PRIMARY KEY,
  regulation INTEGER NOT NULL CHECK (regulation IN (2018, 2023)),
  program TEXT NOT NULL,
  course_code TEXT NOT NULL,
  course_name TEXT NOT NULL,
  credit_hours NUMERIC NOT NULL,
  ects NUMERIC,
  swl NUMERIC,
  lecture_hours NUMERIC,
  tutorial_hours NUMERIC,
  lab_hours NUMERIC,
  total_contact_hours NUMERIC,
  semester INTEGER,
  course_type TEXT,
  concentration_or_track TEXT,
  source_id TEXT NOT NULL REFERENCES academic_sources(source_id),
  source_page INTEGER,
  verification_status TEXT,
  approval_status TEXT NOT NULL,
  approved_by TEXT,
  approved_at DATE,
  notes TEXT,
  UNIQUE (regulation, program, course_code)
);

CREATE TABLE IF NOT EXISTS prerequisite_rules (
  prerequisite_rule_id TEXT PRIMARY KEY,
  course_id TEXT NOT NULL REFERENCES courses(course_id),
  regulation INTEGER NOT NULL,
  program TEXT NOT NULL,
  rule_type TEXT NOT NULL,
  expression JSONB NOT NULL,
  source_text TEXT,
  source_id TEXT NOT NULL REFERENCES academic_sources(source_id),
  source_page INTEGER,
  approval_status TEXT NOT NULL,
  approved_by TEXT,
  approved_at DATE
);

CREATE TABLE IF NOT EXISTS academic_rules (
  rule_id TEXT PRIMARY KEY,
  regulation INTEGER NOT NULL,
  program TEXT NOT NULL,
  rule_type TEXT NOT NULL,
  conditions JSONB NOT NULL,
  result JSONB NOT NULL,
  source_text JSONB,
  source_id TEXT NOT NULL REFERENCES academic_sources(source_id),
  source_page INTEGER,
  approval_status TEXT NOT NULL,
  approved_by TEXT,
  approved_at DATE
);

CREATE TABLE IF NOT EXISTS program_requirements (
  requirement_id TEXT PRIMARY KEY,
  regulation INTEGER NOT NULL,
  program TEXT NOT NULL,
  requirement_type TEXT NOT NULL,
  requirement_group TEXT NOT NULL,
  payload JSONB NOT NULL,
  source_id TEXT NOT NULL REFERENCES academic_sources(source_id),
  source_page INTEGER,
  approval_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS elective_pools (
  pool_id TEXT PRIMARY KEY,
  regulation INTEGER NOT NULL,
  program TEXT NOT NULL,
  pool_name TEXT NOT NULL,
  payload JSONB NOT NULL,
  source_id TEXT NOT NULL REFERENCES academic_sources(source_id),
  approval_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS uel_modules (
  uel_module_id TEXT PRIMARY KEY,
  regulation INTEGER NOT NULL,
  module_code TEXT NOT NULL,
  module_name TEXT NOT NULL,
  credits NUMERIC NOT NULL,
  level INTEGER NOT NULL,
  payload JSONB NOT NULL,
  source_id TEXT NOT NULL REFERENCES academic_sources(source_id),
  approval_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS uel_asu_mapping (
  mapping_id TEXT PRIMARY KEY,
  regulation INTEGER NOT NULL,
  uel_module_id TEXT NOT NULL REFERENCES uel_modules(uel_module_id),
  asu_course_id TEXT NOT NULL,
  mapping_type TEXT NOT NULL,
  weight_percent NUMERIC NOT NULL CHECK (weight_percent >= 0 AND weight_percent <= 100),
  source_id TEXT NOT NULL REFERENCES academic_sources(source_id),
  approval_status TEXT NOT NULL
);

-- Production student-history model. Do not store real private student data in this repository.
CREATE TABLE IF NOT EXISTS students (
  student_id TEXT PRIMARY KEY,
  regulation INTEGER NOT NULL,
  program TEXT NOT NULL,
  track TEXT
);
CREATE TABLE IF NOT EXISTS student_course_attempts (
  student_id TEXT NOT NULL REFERENCES students(student_id),
  course_id TEXT NOT NULL,
  attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
  term TEXT NOT NULL,
  academic_year TEXT NOT NULL,
  grade TEXT,
  grade_points NUMERIC,
  credits_attempted NUMERIC,
  credits_earned NUMERIC,
  status TEXT NOT NULL,
  passed BOOLEAN NOT NULL DEFAULT FALSE,
  failed BOOLEAN NOT NULL DEFAULT FALSE,
  withdrawn BOOLEAN NOT NULL DEFAULT FALSE,
  repeated BOOLEAN NOT NULL DEFAULT FALSE,
  source TEXT,
  PRIMARY KEY (student_id, course_id, attempt_number)
);
CREATE TABLE IF NOT EXISTS current_registrations (
  student_id TEXT NOT NULL REFERENCES students(student_id),
  course_id TEXT NOT NULL,
  term TEXT NOT NULL,
  academic_year TEXT NOT NULL,
  registration_status TEXT NOT NULL,
  PRIMARY KEY (student_id, course_id, term, academic_year)
);
CREATE TABLE IF NOT EXISTS academic_snapshots (
  student_id TEXT NOT NULL REFERENCES students(student_id),
  snapshot_at TIMESTAMPTZ NOT NULL,
  gpa NUMERIC NOT NULL,
  earned_credit_hours NUMERIC NOT NULL,
  registered_credit_hours NUMERIC,
  academic_level TEXT,
  academic_standing TEXT,
  regulation INTEGER NOT NULL,
  program TEXT NOT NULL,
  track TEXT,
  PRIMARY KEY (student_id, snapshot_at)
);
