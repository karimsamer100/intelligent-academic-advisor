"""Typed deterministic facts carried alongside generated advisor text.

The models in this module are built only from successful backend tool
projections.  They are deliberately separate from the provider transcript and
are never populated by inspecting an LLM-generated answer.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _FactsModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class AdvisorPlanningCitation(_FactsModel):
    """Planning provenance associated with one structured academic fact."""

    source_id: str | None = Field(default=None, min_length=1)
    page: int | str | None = None
    rule_id: str | None = Field(default=None, min_length=1)
    approval_status: str | None = Field(default=None, min_length=1)
    verification_status: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _require_provenance_value(self) -> "AdvisorPlanningCitation":
        if self.source_id is None and self.page is None and self.rule_id is None:
            raise ValueError("a planning citation must contain provenance")
        return self


class AdvisorOfficialDocumentEvidence(_FactsModel):
    """One actual RAG result, without claims about semantic support."""

    source_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    score: float | None = None
    chunk_id: str | None = Field(default=None, min_length=1)
    file_name: str | None = Field(default=None, min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, min_length=1)
    document_type: str | None = Field(default=None, min_length=1)
    regulation: int | None = None
    program: str | None = Field(default=None, min_length=1)
    language: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _validate_page_range(self) -> "AdvisorOfficialDocumentEvidence":
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class AdvisorToolAuthority(_FactsModel):
    """Authority/review semantics for one successful tool result.

    ``None`` is intentional for course-information and RAG facts: those tools
    do not produce a student eligibility decision or a formal Planning review
    flag.
    """

    call_id: str = Field(min_length=1)
    tool_name: Literal[
        "check_course_eligibility",
        "get_course_information",
        "degree_audit",
        "search_official_documents",
    ]
    source: Literal["PLANNING", "RAG"]
    authoritative: bool | None = None
    requires_human_review: bool | None = None
    limitations: list[str] = Field(default_factory=list)


class AdvisorEligibilityFacts(_FactsModel):
    """The exact compact eligibility projection for one tool execution."""

    call_id: str = Field(min_length=1)
    course: dict[str, Any]
    decision: str = Field(min_length=1)
    status: str = Field(min_length=1)
    eligible: bool | None
    authoritative: bool
    requires_human_review: bool
    rule_set_status: str = Field(min_length=1)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_requirements: list[dict[str, str]] = Field(default_factory=list)
    conditions: list[dict[str, str]] = Field(default_factory=list)
    citations: list[AdvisorPlanningCitation] = Field(default_factory=list)


class AdvisorCourseInformationFacts(_FactsModel):
    """Static structured course facts, independent of student history."""

    call_id: str = Field(min_length=1)
    course: dict[str, Any]
    prerequisites: dict[str, Any]
    corequisites: dict[str, Any]
    coverage: dict[str, str]
    data_source: dict[str, Any]
    course_provenance: list[AdvisorPlanningCitation] = Field(default_factory=list)
    authoritative: bool


class AdvisorRequirementFacts(_FactsModel):
    """Bounded requirement-level audit facts and their own provenance."""

    id: str = Field(min_length=1)
    type: str | None = None
    outcome: str = Field(min_length=1)
    requires_human_review: bool
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: list[AdvisorPlanningCitation] = Field(default_factory=list)
    course_code: str | None = Field(default=None, min_length=1)


class AdvisorRequirementSummary(_FactsModel):
    satisfied_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    satisfied_ids: list[str] = Field(default_factory=list)
    remaining_ids: list[str] = Field(default_factory=list)
    review_ids: list[str] = Field(default_factory=list)
    details: list[AdvisorRequirementFacts] = Field(default_factory=list)
    details_truncated: bool = False


class AdvisorDegreeAuditFacts(_FactsModel):
    """Compact degree-audit facts with requirement-level review boundaries."""

    call_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    requirement_set_status: str = Field(min_length=1)
    authoritative: bool
    requires_human_review: bool
    reasons: list[str] = Field(default_factory=list)
    credits: dict[str, int | float | None]
    requirements: AdvisorRequirementSummary
    mandatory_missing_courses: list[str] = Field(default_factory=list)
    elective_progress: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    citations: list[AdvisorPlanningCitation] = Field(default_factory=list)


class AdvisorOfficialDocumentFacts(_FactsModel):
    """RAG evidence facts; an empty result is explicitly not evidence."""

    call_id: str = Field(min_length=1)
    results: list[AdvisorOfficialDocumentEvidence] = Field(default_factory=list)
    evidence_available: bool
    coverage_status: Literal["AVAILABLE", "NO_EVIDENCE", "INCOMPLETE"]
    invalid_evidence_count: int = Field(default=0, ge=0)


class AdvisorAcademicFacts(_FactsModel):
    """Structured facts grouped by authority and responsibility."""

    eligibility: list[AdvisorEligibilityFacts] = Field(default_factory=list)
    course_information: list[AdvisorCourseInformationFacts] = Field(
        default_factory=list
    )
    degree_audit: list[AdvisorDegreeAuditFacts] = Field(default_factory=list)
    official_documents: list[AdvisorOfficialDocumentFacts] = Field(
        default_factory=list
    )
    authority: list[AdvisorToolAuthority] = Field(default_factory=list)


class AdvisorGroundingAssessment(_FactsModel):
    """Result of narrow deterministic checks over generated text."""

    status: Literal["NO_TRUSTED_FACTS", "GROUNDED", "SAFE_FALLBACK"] = (
        "NO_TRUSTED_FACTS"
    )
    issues: list[str] = Field(default_factory=list)


def build_advisor_academic_facts(
    executions: Iterable[Any],
) -> AdvisorAcademicFacts:
    """Build frontend-facing facts from successful trusted tool results only."""

    eligibility: list[AdvisorEligibilityFacts] = []
    course_information: list[AdvisorCourseInformationFacts] = []
    degree_audit: list[AdvisorDegreeAuditFacts] = []
    official_documents: list[AdvisorOfficialDocumentFacts] = []
    authority: list[AdvisorToolAuthority] = []

    for execution in executions:
        if getattr(execution, "status", None) != "executed":
            continue
        result = getattr(execution, "result", None)
        if not isinstance(result, Mapping) or "error" in result:
            continue
        tool_name = getattr(execution, "tool_name", None)
        call_id = getattr(execution, "call_id", None)
        if not isinstance(tool_name, str) or not isinstance(call_id, str):
            continue

        if tool_name == "check_course_eligibility":
            fact = _validate_fact(
                AdvisorEligibilityFacts,
                {"call_id": call_id, **_pick(result, AdvisorEligibilityFacts)},
            )
            if fact is not None:
                eligibility.append(fact)
                authority.append(
                    AdvisorToolAuthority(
                        call_id=call_id,
                        tool_name=tool_name,
                        source="PLANNING",
                        authoritative=fact.authoritative,
                        requires_human_review=fact.requires_human_review,
                        limitations=_planning_limitations(
                            fact.authoritative,
                            fact.rule_set_status,
                            fact.requires_human_review,
                        ),
                    )
                )
            continue

        if tool_name == "get_course_information":
            fact = _validate_fact(
                AdvisorCourseInformationFacts,
                {"call_id": call_id, **_pick(result, AdvisorCourseInformationFacts)},
            )
            if fact is not None:
                course_information.append(fact)
                authority.append(
                    AdvisorToolAuthority(
                        call_id=call_id,
                        tool_name=tool_name,
                        source="PLANNING",
                        authoritative=fact.authoritative,
                        requires_human_review=None,
                        limitations=_coverage_limitations(fact.coverage),
                    )
                )
            continue

        if tool_name == "degree_audit":
            fact = _validate_fact(
                AdvisorDegreeAuditFacts,
                {"call_id": call_id, **_pick(result, AdvisorDegreeAuditFacts)},
            )
            if fact is not None:
                degree_audit.append(fact)
                authority.append(
                    AdvisorToolAuthority(
                        call_id=call_id,
                        tool_name=tool_name,
                        source="PLANNING",
                        authoritative=fact.authoritative,
                        requires_human_review=fact.requires_human_review,
                        limitations=_planning_limitations(
                            fact.authoritative,
                            fact.requirement_set_status,
                            fact.requires_human_review,
                        ),
                    )
                )
            continue

        if tool_name == "search_official_documents":
            fact = _document_facts(call_id, result)
            if fact is not None:
                official_documents.append(fact)
                authority.append(
                    AdvisorToolAuthority(
                        call_id=call_id,
                        tool_name=tool_name,
                        source="RAG",
                        authoritative=None,
                        requires_human_review=None,
                        limitations=(
                            [fact.coverage_status]
                            if fact.coverage_status != "AVAILABLE"
                            else []
                        ),
                    )
                )

    return AdvisorAcademicFacts(
        eligibility=eligibility,
        course_information=course_information,
        degree_audit=degree_audit,
        official_documents=official_documents,
        authority=authority,
    )


def _pick(result: Mapping[str, Any], model: type[BaseModel]) -> dict[str, Any]:
    return {
        name: result[name]
        for name in model.model_fields
        if name != "call_id" and name in result
    }


def _validate_fact(model: type[BaseModel], payload: Mapping[str, Any]) -> Any | None:
    try:
        return model.model_validate(payload)
    except (TypeError, ValueError):
        return None


def _document_facts(
    call_id: str,
    result: Mapping[str, Any],
) -> AdvisorOfficialDocumentFacts | None:
    raw_results = result.get("results")
    if not isinstance(raw_results, list):
        return None
    valid_results: list[AdvisorOfficialDocumentEvidence] = []
    invalid_count = 0
    for item in raw_results[:20]:
        if not isinstance(item, Mapping):
            invalid_count += 1
            continue
        fact = _validate_fact(AdvisorOfficialDocumentEvidence, item)
        if fact is None:
            invalid_count += 1
        else:
            valid_results.append(fact)
    status: Literal["AVAILABLE", "NO_EVIDENCE", "INCOMPLETE"]
    if invalid_count:
        status = "INCOMPLETE"
    elif valid_results:
        status = "AVAILABLE"
    else:
        status = "NO_EVIDENCE"
    return AdvisorOfficialDocumentFacts(
        call_id=call_id,
        results=valid_results,
        evidence_available=bool(valid_results),
        coverage_status=status,
        invalid_evidence_count=invalid_count,
    )


def _planning_limitations(
    authoritative: bool,
    coverage_status: str,
    requires_human_review: bool,
) -> list[str]:
    limitations: list[str] = []
    if not authoritative:
        limitations.append("NON_AUTHORITATIVE_DATA")
    if coverage_status != "COMPLETE":
        limitations.append(coverage_status)
    if requires_human_review:
        limitations.append("FORMAL_REVIEW_REPORTED")
    return limitations


def _coverage_limitations(coverage: Mapping[str, str]) -> list[str]:
    return [
        f"{name.upper()}_{status}"
        for name, status in coverage.items()
        if isinstance(status, str) and status != "AVAILABLE"
    ]


__all__ = [
    "AdvisorAcademicFacts",
    "AdvisorToolAuthority",
    "AdvisorCourseInformationFacts",
    "AdvisorDegreeAuditFacts",
    "AdvisorEligibilityFacts",
    "AdvisorGroundingAssessment",
    "AdvisorOfficialDocumentEvidence",
    "AdvisorOfficialDocumentFacts",
    "AdvisorPlanningCitation",
    "AdvisorRequirementFacts",
    "AdvisorRequirementSummary",
    "build_advisor_academic_facts",
]
