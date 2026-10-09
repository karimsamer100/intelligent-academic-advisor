from __future__ import annotations

from collections.abc import Iterable

SUPPORTED_DOCUMENT_TYPES = frozenset(
    {
        "COURSE_HANDBOOK",
        "COURSE_TREE",
        "ELECTIVE_PREREQUISITES",
        "MODULE_SPEC",
        "PORTFOLIO_TEMPLATE",
        "PREREQUISITE_DRAFT",
        "PROCEDURE",
        "PROGRAM_STRUCTURE",
        "REGULATION",
        "TRAINING_HANDBOOK",
    }
)

DOCUMENT_TYPE_MAP = {
    "regulation": "REGULATION",
    "regulations": "REGULATION",
    "academic regulation": "REGULATION",
    "academic regulations": "REGULATION",
    "full academic regulation": "REGULATION",
    "bylaw summary / rules": "REGULATION",
    "general rules & regulations": "REGULATION",
    "rules and regulations": "REGULATION",
    "course handbook": "COURSE_HANDBOOK",
    "collaborative course handbook": "COURSE_HANDBOOK",
    "course tree": "COURSE_TREE",
    "course tree / study plan": "COURSE_TREE",
    "caie course tree / study plan": "COURSE_TREE",
    "study plan": "COURSE_TREE",
    "elective prerequisites": "ELECTIVE_PREREQUISITES",
    "elective course tree / prerequisites": "ELECTIVE_PREREQUISITES",
    "module spec": "MODULE_SPEC",
    "module specifications": "MODULE_SPEC",
    "portfolio template": "PORTFOLIO_TEMPLATE",
    "prerequisite draft": "PREREQUISITE_DRAFT",
    "prerequisite draft list": "PREREQUISITE_DRAFT",
    "procedure": "PROCEDURE",
    "procedures": "PROCEDURE",
    "student guideline booklet": "PROCEDURE",
    "training application guide": "PROCEDURE",
    "training application tutorial": "PROCEDURE",
    "program structure": "PROGRAM_STRUCTURE",
    "program structure / module mapping": "PROGRAM_STRUCTURE",
    "training handbook": "TRAINING_HANDBOOK",
}


def canonical_document_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split()).casefold()
    return DOCUMENT_TYPE_MAP.get(normalized, value.strip().upper().replace(" ", "_"))


def canonical_document_type_filter(value: str) -> str:
    """Return a supported search filter or reject an unknown category."""

    canonical = canonical_document_type(value)
    if canonical not in SUPPORTED_DOCUMENT_TYPES:
        raise ValueError(f"Unsupported document type filter: {value}")
    return canonical


def canonical_document_type_filters(values: Iterable[str]) -> list[str]:
    """Canonicalize and de-duplicate an explicit list of search filters."""

    canonical_values: list[str] = []
    for value in values:
        canonical = canonical_document_type_filter(value)
        if canonical not in canonical_values:
            canonical_values.append(canonical)
    return canonical_values


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
