"""Small, explicit live evaluator for the complete grounded advisor path.

This module is intentionally outside the ordinary backend test tree.  It is
run only by an explicit command when the configured Ollama service is
available.  Discovery and tool execution use the same application-owned
composition and request-scoped RAG lifecycle as the future HTTP boundary.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from fastapi import Request
from fastapi.testclient import TestClient

from app.api.deps import get_advisor_static_dependencies, get_llm_provider
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.llm.contracts import GenerationRequest, GenerationResponse, ToolCall
from app.llm.errors import LLMProviderError
from app.llm.interface import LLMProvider
from app.main import create_app
from app.orchestration.composition import (
    AdvisorApplication,
    AdvisorStaticDependencies,
    build_advisor_application,
)
from app.orchestration.contracts import AdvisorRequest, AdvisorResponse
from app.rag.provider import get_retriever
from app.schemas.rag import RAGRequest
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService
from app.tools.context import ToolExecutionContext
from app.tools.factory import build_academic_tool_registry

from evaluator import grade_turn, skip_case


EXIT_CODES = {
    "PASS": 0,
    "FAIL": 1,
    "BLOCKED": 2,
    "SKIPPED": 2,
    "NEEDS_MANUAL_REVIEW": 3,
}
_ALLOWED_ARGUMENT_KEYS = {
    "check_course_eligibility": {"course_code"},
    "degree_audit": set(),
    "search_official_documents": {"query", "document_types"},
}
_MAX_COURSE_PROBES = 200
_GPA_RE = re.compile(
    r"\b(?:gpa|grade point average)\s*(?:is|:|=)?\s*\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)
_CREDIT_TOTAL_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?\s+of\s+\d+|\d+(?:\.\d+)?)\s+"
    r"(?:credits?|credit hours?)\b",
    re.IGNORECASE,
)
_ARABIC_CREDIT_TOTAL_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ساعات|ساعة|وحدات)"
)


class EvaluationBlocked(RuntimeError):
    """A required live dependency or trusted discovery source is unavailable."""


@dataclass(frozen=True, slots=True)
class Discovery:
    """Safe discovery facts plus the internal trusted student identifier."""

    student_id: str
    regulation: int
    program: str
    course_codes: tuple[str, ...]
    eligibility_course: str | None
    review_course: str | None
    student_count: int
    valid_student_count: int
    rag_available: bool
    rag_reason: str


@dataclass(frozen=True, slots=True)
class ProviderCall:
    request: GenerationRequest
    response: GenerationResponse | None
    error: BaseException | None
    latency_ms: float


class RecordingProvider:
    """Record provider-neutral calls without retaining raw prompts in output."""

    def __init__(self, delegate: LLMProvider) -> None:
        self._delegate = delegate
        self.calls: list[ProviderCall] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        started = time.perf_counter()
        try:
            response = self._delegate.generate(request)
        except BaseException as error:  # noqa: BLE001 - runner records safe status
            self.calls.append(
                ProviderCall(
                    request=request,
                    response=None,
                    error=error,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
            raise

        self.calls.append(
            ProviderCall(
                request=request,
                response=response,
                error=None,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        )
        return response

    def generate_structured(self, request: Any, response_model: Any) -> Any:
        return self._delegate.generate_structured(request, response_model)


@contextmanager
def _request_scoped_rag() -> Iterator[RAGService]:
    """Create and close exactly one DB-backed retriever for one request."""

    database_generator = get_db()
    try:
        database_session = next(database_generator)
        yield RAGService(retriever=get_retriever(database_session))
    finally:
        database_generator.close()


def _load_cases(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationBlocked("evaluation cases are unavailable") from error

    cases = payload.get("cases") if isinstance(payload, Mapping) else None
    if not isinstance(cases, list) or not all(isinstance(item, Mapping) for item in cases):
        raise EvaluationBlocked("evaluation cases are invalid")
    return [dict(item) for item in cases]


def _student_ids(path: Path) -> tuple[str, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationBlocked("trusted student source is unavailable") from error

    rows = payload if isinstance(payload, list) else payload.get("students", [])
    if not isinstance(rows, list):
        raise EvaluationBlocked("trusted student source is invalid")
    identifiers = tuple(
        str(row["student_id"])
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("student_id"), str)
    )
    if not identifiers:
        raise EvaluationBlocked("no trusted development students were discovered")
    return identifiers


def _ordered_course_codes(codes: Sequence[str]) -> list[str]:
    preferred = [code for code in ("CSE221", "CSE241") if code in codes]
    return preferred + [code for code in sorted(codes) if code not in preferred]


def _discover_rag(
    *,
    student_id: str,
    regulation: int,
    program: str,
) -> tuple[bool, str]:
    try:
        with _request_scoped_rag() as rag_service:
            response = rag_service.search(
                RAGRequest(
                    query="official academic regulations for course registration and program completion",
                    student_id=student_id,
                    regulation=regulation,
                    program=program,
                    document_types=["REGULATION"],
                )
            )
    except Exception:  # noqa: BLE001 - discovery becomes an explicit limitation
        return False, "dependency_unavailable"
    if not response.results:
        return False, "no_regulation_evidence_discovered"
    return True, "evidence_available"


def _discover(
    *,
    settings: Settings,
    static_dependencies: AdvisorStaticDependencies,
) -> Discovery:
    identifiers = _student_ids(settings.student_data_path)
    valid_student_count = 0
    selected: tuple[str, Any, tuple[str, ...]] | None = None

    for student_id in identifiers:
        try:
            student = static_dependencies.student_repository.get_student_state(student_id)
            if student is None:
                continue
            courses = static_dependencies.academic_data.list_courses(
                regulation=student.regulation,
                program=student.program,
            )
        except Exception:  # noqa: BLE001 - try the next trusted development row
            continue
        valid_student_count += 1
        course_codes = tuple(
            sorted({course.identity.course_code for course in courses})
        )
        if course_codes and selected is None:
            selected = (student_id, student, course_codes)

    if selected is None:
        raise EvaluationBlocked("no trusted student with supported courses was discovered")

    student_id, student, course_codes = selected
    registry = build_academic_tool_registry(
        planning_service=static_dependencies.planning_service,
        rag_service=RAGService(),
        student_repository=static_dependencies.student_repository,
        academic_data=static_dependencies.academic_data,
    )
    context = ToolExecutionContext(student_id=student_id)
    eligibility_course: str | None = None
    review_course: str | None = None
    for course_code in _ordered_course_codes(course_codes)[:_MAX_COURSE_PROBES]:
        try:
            result = registry.execute(
                "check_course_eligibility",
                {"course_code": course_code},
                context,
            )
        except Exception:  # noqa: BLE001 - unsupported rows are not invented
            continue
        if result.get("requires_human_review") is True:
            review_course = review_course or course_code
        else:
            eligibility_course = eligibility_course or course_code
        if eligibility_course and review_course:
            break

    rag_available, rag_reason = _discover_rag(
        student_id=student_id,
        regulation=student.regulation.year,
        program=str(student.program),
    )
    return Discovery(
        student_id=student_id,
        regulation=student.regulation.year,
        program=str(student.program),
        course_codes=course_codes,
        eligibility_course=eligibility_course,
        review_course=review_course,
        student_count=len(identifiers),
        valid_student_count=valid_student_count,
        rag_available=rag_available,
        rag_reason=rag_reason,
    )


def _render_prompt(template: str, discovery: Discovery) -> str:
    return (
        template.replace("{{eligibility_course}}", discovery.eligibility_course or "")
        .replace("{{review_course}}", discovery.review_course or "")
    )


def _missing_prerequisites(
    case: Mapping[str, Any],
    discovery: Discovery,
) -> list[str]:
    available = {
        "eligibility_course": discovery.eligibility_course is not None,
        "review_course": discovery.review_course is not None,
        "rag_available": discovery.rag_available,
    }
    return [
        str(requirement)
        for requirement in case.get("requires", [])
        if not available.get(str(requirement), False)
    ]


def _bounded_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:300]
    if isinstance(value, list):
        return [_bounded_value(item) for item in value[:20]]
    if isinstance(value, Mapping):
        return {str(key): _bounded_value(item) for key, item in value.items()}
    return value


def _redact_student_sensitive_text(
    text: str,
    student_id: str | None = None,
) -> str:
    redacted = text
    if student_id:
        redacted = redacted.replace(student_id, "[redacted-student]")
    redacted = _GPA_RE.sub("[redacted-gpa]", redacted)
    redacted = _CREDIT_TOTAL_RE.sub("[redacted-credits]", redacted)
    return _ARABIC_CREDIT_TOTAL_RE.sub("[redacted-credits]", redacted)


def _safe_report_prompt(
    prompt: str | None,
    student_id: str | None = None,
) -> str | None:
    """Redact a prompt only when it crosses into persisted evaluation output."""

    if prompt is None:
        return None
    return _redact_student_sensitive_text(prompt, student_id)


def _case_report_prompt(
    case: Mapping[str, Any],
    discovery: Discovery | None = None,
) -> str | None:
    if discovery is None:
        return None
    template = case.get("prompt")
    if not isinstance(template, str):
        return None
    rendered = _render_prompt(template, discovery)
    return _safe_report_prompt(rendered, discovery.student_id)


def _safe_arguments(tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    allowed = _ALLOWED_ARGUMENT_KEYS.get(tool_name, set())
    safe = {
        key: _bounded_value(arguments[key])
        for key in sorted(arguments)
        if key in allowed
    }
    rejected = sorted(set(arguments) - allowed)
    if rejected:
        safe["rejected_argument_keys"] = rejected
    return safe


def _tool_call_payload(calls: Sequence[ToolCall]) -> list[dict[str, Any]]:
    return [
        {"name": call.name, "arguments": _safe_arguments(call.name, call.arguments)}
        for call in calls
    ]


def _safe_tool_summary(result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, Mapping):
        return None
    if "error" in result:
        return {"error": _bounded_value(result.get("error"))}
    summary: dict[str, Any] = {}
    for key in (
        "decision",
        "status",
        "eligible",
        "authoritative",
        "requires_human_review",
        "rule_set_status",
        "requirement_set_status",
        "reasons",
        "warnings",
        "citations",
    ):
        if key in result:
            summary[key] = _bounded_value(result[key])
    summary["student_specific_details_redacted"] = True
    if isinstance(result.get("results"), list):
        summary["results"] = [
            {
                key: _bounded_value(item[key])
                for key in (
                    "source_id",
                    "page_start",
                    "page_end",
                    "document_type",
                    "text",
                )
                if key in item
            }
            for item in result["results"][:10]
            if isinstance(item, Mapping)
        ]
    return summary


def _safe_error(error: BaseException) -> dict[str, str]:
    if isinstance(error, LLMProviderError):
        return {"type": type(error).__name__, "message": str(error)}
    return {"type": type(error).__name__, "message": "evaluation dependency failed"}


def _initial_tool_calls(provider: RecordingProvider) -> list[ToolCall]:
    if not provider.calls or provider.calls[0].response is None:
        return []
    return list(provider.calls[0].response.tool_calls)


def _tool_calls_by_round(provider: RecordingProvider) -> list[list[ToolCall]]:
    return [
        list(call.response.tool_calls)
        for call in provider.calls
        if call.response is not None
    ]


def _blocked_case_result(
    *,
    case: Mapping[str, Any],
    prompt: str,
    student_id: str | None,
    provider: RecordingProvider | None,
    response: AdvisorResponse | None,
    error: BaseException,
) -> dict[str, Any]:
    requested_rounds = _tool_calls_by_round(provider) if provider is not None else []
    calls = [call for round_calls in requested_rounds for call in round_calls]
    executions = list(response.tool_executions) if response is not None else []
    executed = [
        execution for execution in executions if execution.status in {"executed", "failed"}
    ]
    summaries = [
        _safe_tool_summary(execution.result)
        for execution in executions
        if execution.result is not None
    ]
    summaries = [summary for summary in summaries if summary is not None]
    available_result = any(
        isinstance(execution.result, Mapping) and "error" not in execution.result
        for execution in executed
    )
    return {
        "case_id": str(case["id"]),
        "prompt": _safe_report_prompt(prompt, student_id),
        "language_expected": case.get("language_expected"),
        "status": "BLOCKED",
        "selected_tools": [call.name for call in calls],
        "requested_tools_by_round": [
            _tool_call_payload(round_calls) for round_calls in requested_rounds
        ],
        "executed_tools": [
            {
                "tool_name": execution.tool_name,
                "status": execution.status,
                "round_index": execution.round_index,
                "arguments": _safe_arguments(execution.tool_name, execution.arguments),
                "result": _safe_tool_summary(execution.result),
            }
            for execution in executed
        ],
        "rejected_tool_calls": [
            {
                "tool_name": execution.tool_name,
                "status": execution.status,
                "round_index": execution.round_index,
                "arguments": _safe_arguments(execution.tool_name, execution.arguments),
                "result": _safe_tool_summary(execution.result),
            }
            for execution in executions
            if execution.status == "rejected"
        ],
        "tool_arguments": _tool_call_payload(calls),
        "tool_selected": calls[0].name if len(calls) == 1 else None,
        "tool_executed": bool(executed),
        "tool_execution_count": len(executed),
        "tool_round_count": len(requested_rounds),
        "tool_result_available": available_result,
        "trusted_tool_summary": summaries[0] if len(summaries) == 1 else None,
        "trusted_tool_summaries": summaries,
        "final_answer": None,
        "response_language": None,
        "decision_preserved": None,
        "human_review_preserved": None,
        "citations_supported": None,
        "invented_academic_information": [],
        "latency_ms": round(
            sum(call.latency_ms for call in provider.calls), 2
        ) if provider is not None else 0.0,
        "provider_call_count": len(provider.calls) if provider is not None else 0,
        "provider_error": _safe_error(error),
        "reasons": ["live_dependency_unavailable"],
    }


def _run_case(
    *,
    request_scope: Request,
    settings: Settings,
    static_dependencies: AdvisorStaticDependencies,
    discovery: Discovery,
    case: Mapping[str, Any],
) -> dict[str, Any]:
    template = str(case.get("prompt", ""))
    prompt = _render_prompt(template, discovery)
    provider: RecordingProvider | None = None
    response: AdvisorResponse | None = None
    started = time.perf_counter()
    try:
        with _request_scoped_rag() as rag_service:
            provider = RecordingProvider(get_llm_provider(request_scope))
            application: AdvisorApplication = build_advisor_application(
                llm_service=LLMService(provider),
                planning_service=static_dependencies.planning_service,
                rag_service=rag_service,
                student_repository=static_dependencies.student_repository,
                academic_data=static_dependencies.academic_data,
            )
            response = application.orchestrator.respond(
                AdvisorRequest(user_message=prompt, student_id=discovery.student_id)
            )
    except BaseException as error:  # noqa: BLE001 - live runner must fail safely
        return _blocked_case_result(
            case=case,
            prompt=prompt,
            student_id=discovery.student_id,
            provider=provider,
            response=response,
            error=error,
        )

    assert provider is not None
    if any(call.error is not None for call in provider.calls):
        provider_error = next(
            call.error for call in provider.calls if call.error is not None
        )
        assert provider_error is not None
        return _blocked_case_result(
            case=case,
            prompt=prompt,
            student_id=discovery.student_id,
            provider=provider,
            response=response,
            error=provider_error,
        )
    assert response is not None

    initial_calls = _initial_tool_calls(provider)
    graded = grade_turn(
        case=case,
        response=response,
        initial_tool_calls=initial_calls,
        tool_calls_by_round=_tool_calls_by_round(provider),
        known_course_codes=discovery.course_codes,
    )
    graded["prompt"] = _safe_report_prompt(prompt, discovery.student_id)
    graded["final_answer"] = _redact_student_sensitive_text(
        str(graded["final_answer"]), discovery.student_id
    )
    graded["language_expected"] = case.get("language_expected")
    graded["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    graded["provider_call_count"] = len(provider.calls)
    graded["model"] = next(
        (
            call.response.model
            for call in provider.calls
            if call.response is not None and call.response.model
        ),
        settings.llm_model,
    )
    graded["final_request_had_no_tools"] = bool(
        provider.calls and not provider.calls[-1].request.tools
    )
    graded["final_response_had_tool_calls"] = bool(
        provider.calls
        and provider.calls[-1].response is not None
        and provider.calls[-1].response.tool_calls
    )
    graded["provider_call_latencies_ms"] = [
        round(call.latency_ms, 2) for call in provider.calls
    ]
    graded["provider_generation_count"] = len(provider.calls)
    if len(provider.calls) > 4:
        graded["status"] = "FAIL"
        graded["reasons"].append("orchestration_generation_bound_exceeded")
    return graded


def _safe_discovery(discovery: Discovery) -> dict[str, Any]:
    return {
        "student_count": discovery.student_count,
        "valid_student_count": discovery.valid_student_count,
        "regulation": discovery.regulation,
        "program": discovery.program,
        "supported_course_count": len(discovery.course_codes),
        "eligibility_course": discovery.eligibility_course,
        "human_review_course": discovery.review_course,
        "rag_available": discovery.rag_available,
        "rag_reason": discovery.rag_reason,
    }


def _aggregate_status(results: Sequence[Mapping[str, Any]]) -> str:
    statuses = {str(result.get("status")) for result in results}
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if "FAIL" in statuses:
        return "FAIL"
    if "NEEDS_MANUAL_REVIEW" in statuses:
        return "NEEDS_MANUAL_REVIEW"
    if "SKIPPED" in statuses:
        return "SKIPPED"
    return "PASS"


def _summary(results: Sequence[Mapping[str, Any]], status: str) -> dict[str, Any]:
    counts = {name: 0 for name in EXIT_CODES}
    for result in results:
        result_status = str(result.get("status"))
        if result_status in counts:
            counts[result_status] += 1
    return {"status": status, "counts": counts, "total_cases": len(results)}


def _blocked_payload(cases: Sequence[Mapping[str, Any]], reason: str) -> dict[str, Any]:
    results = [
        skip_case(
            str(case.get("id", "unknown")),
            reason,
            prompt=_case_report_prompt(case),
        )
        for case in cases
    ]
    results = [dict(result, status="BLOCKED", skip_reason=reason) for result in results]
    return {
        "schema_version": "orchestration-live-eval-v2",
        "evaluation": "grounded-advisor-orchestration",
        "status": "BLOCKED",
        "model": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "discovery": {"status": "unavailable", "reason": reason},
        "cases": results,
        "summary": _summary(results, "BLOCKED"),
    }


def _select_cases(
    cases: Sequence[Mapping[str, Any]],
    case_ids: Sequence[str] | None,
) -> list[dict[str, Any]]:
    if not case_ids:
        return [dict(case) for case in cases]
    by_id = {str(case.get("id")): dict(case) for case in cases}
    missing = [case_id for case_id in case_ids if case_id not in by_id]
    if missing:
        raise EvaluationBlocked("requested case is unavailable: " + ",".join(missing))
    return [by_id[case_id] for case_id in case_ids]


def run_evaluation(
    cases_path: Path,
    *,
    case_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run the complete live path and return a safe, bounded result payload."""

    try:
        all_cases = _load_cases(cases_path)
        cases = _select_cases(all_cases, case_ids)
        settings = get_settings()
    except EvaluationBlocked as error:
        return _blocked_payload([], str(error))
    except Exception:
        return _blocked_payload([], "application configuration unavailable")
    try:
        with TestClient(create_app()) as client:
            runtime_app = client.app
            request_scope = Request({"type": "http", "app": runtime_app})
            static_dependencies = get_advisor_static_dependencies(request_scope)
            discovery = _discover(
                settings=settings,
                static_dependencies=static_dependencies,
            )
            results: list[dict[str, Any]] = []
            for case_index, case in enumerate(cases):
                missing = _missing_prerequisites(case, discovery)
                if missing:
                    results.append(
                        skip_case(
                            str(case["id"]),
                            "missing_prerequisite:" + ",".join(missing),
                            prompt=_case_report_prompt(case, discovery),
                        )
                    )
                    continue
                result = _run_case(
                    request_scope=request_scope,
                    settings=settings,
                    static_dependencies=static_dependencies,
                    discovery=discovery,
                    case=case,
                )
                results.append(result)
                if result["status"] == "BLOCKED":
                    results.extend(
                        skip_case(
                            str(remaining_case["id"]),
                            "previous_case_blocked",
                            prompt=_case_report_prompt(remaining_case, discovery),
                        )
                        for remaining_case in cases[case_index + 1 :]
                    )
                    break

            status = _aggregate_status(results)
            return {
                "schema_version": "orchestration-live-eval-v2",
                "evaluation": "grounded-advisor-orchestration",
                "status": status,
                "model": settings.llm_model,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "discovery": _safe_discovery(discovery),
                "cases": results,
                "summary": _summary(results, status),
            }
    except EvaluationBlocked as error:
        return _blocked_payload(cases, str(error))
    except Exception:
        return _blocked_payload(cases, "application dependency unavailable")


def _default_output_path() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(__file__).parent / "results" / f"orchestration-{timestamp}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("cases.json"),
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--case-id",
        action="append",
        default=None,
        help="Run only the selected case ID; repeat the option for multiple cases.",
    )
    args = parser.parse_args()

    payload = run_evaluation(args.cases, case_ids=args.case_id)
    output_path = args.output or _default_output_path()
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        print("Evaluation result could not be written.")
        return 2

    print(
        json.dumps(
            {
                "status": payload["status"],
                "output": str(output_path),
                "summary": payload["summary"],
            },
            ensure_ascii=False,
        )
    )
    return EXIT_CODES[str(payload["status"])]


if __name__ == "__main__":
    raise SystemExit(main())
