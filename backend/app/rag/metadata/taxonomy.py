from __future__ import annotations

DOCUMENT_TYPE_MAP = {
    "full academic regulation": "REGULATION",
    "bylaw summary / rules": "REGULATION",
    "general rules & regulations": "REGULATION",
    "collaborative course handbook": "COURSE_HANDBOOK",
    "student guideline booklet": "PROCEDURE",
    "training application tutorial": "PROCEDURE",
    "training handbook": "TRAINING_HANDBOOK",
    "module specifications": "MODULE_SPEC",
}


def canonical_document_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split()).casefold()
    return DOCUMENT_TYPE_MAP.get(normalized, value.strip().upper().replace(" ", "_"))


TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "credit_load": ("credit load", "credit hours", "register for", "course registration rules", "academic load"),
    "registration": ("registration", "register", "enrolment", "enrollment", "add/drop", "add drop"),
    "prerequisites": ("prerequisite", "pre-requisite", "co-requisite", "corequisite"),
    "graduation": ("graduation requirements", "graduate", "graduation project", "degree requirements"),
    "academic_standing": ("academic warning", "dismissal", "cumulative gpa", "academic standing"),
    "training": ("field training", "training", "industrial training"),
    "assessment": ("assessment", "grading", "midterm", "final exam", "portfolio"),
    "electives": ("elective", "concentration", "minor program"),
    "program_structure": ("program structure", "program duration", "program requirements", "level"),
    "student_procedure": ("procedure", "guideline", "submission", "help request", "upload"),
}
