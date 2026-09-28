"""Explicit, non-CI evaluation runner for the configured Ollama model.

The ordinary cases use the production path:

    LLMService -> OllamaProvider -> /api/chat

The context, thinking, and runtime-metadata probes use direct HTTP only to
exercise Ollama request fields that are intentionally not part of the current
provider-neutral application contract. They are evaluation-only probes and do
not execute academic tools.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Literal, Mapping, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings, get_settings
from app.llm.contracts import (
    GenerationRequest,
    LLMMessage,
    MessageRole,
    ToolDefinition,
)
from app.llm.errors import LLMProviderError
from app.llm.providers.ollama import OllamaProvider
from app.services.llm_service import LLMService
from app.tools.factory import build_academic_tool_registry
from app.tools.registry import ToolRegistry


ToolExpectation = str | None
_DEFAULT_THINK = object()


class StructuredEvaluation(BaseModel):
    """Small schema used only by the live structured-output cases."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    language: Literal["en", "ar", "mixed"]
    topic: Literal["greeting", "academic"]
    needs_grounding: bool


def _load_cases(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("cases file must contain a JSON object")
    return payload


def _tool_registry_for_definitions() -> ToolRegistry:
    """Build current definitions without creating executable dependencies.

    Selection evaluation never executes a tool. The composition factory is
    still used so the eval cannot drift from the frozen application tool set.
    """

    dependency = object()
    return build_academic_tool_registry(
        planning_service=cast(Any, dependency),
        rag_service=cast(Any, dependency),
        student_repository=cast(Any, dependency),
        academic_data=cast(Any, dependency),
    )


def _make_service(settings: Settings) -> tuple[LLMService, httpx.Client]:
    client = httpx.Client(timeout=settings.llm_timeout_seconds)
    return LLMService(OllamaProvider(settings=settings, client=client)), client


def _base_system_instruction() -> str:
    return (
        "You are a careful academic assistant. Use an available tool whenever "
        "the request needs institutional rules, official documents, or the "
        "student's actual academic record. Never invent GPA, credits, courses, "
        "attempts, registration, regulation, program, or other trusted facts. "
        "The only student-facing tool inputs are course_code for "
        "check_course_eligibility, no arguments for degree_audit, and query plus "
        "optional document_types/language for search_official_documents. Never "
        "put student_id or trusted academic facts in tool arguments. If the "
        "request is unclear, ask a clarification question without calling a "
        "tool. Greetings and unrelated general questions do not need a tool."
    )


def _request_for_prompt(
    prompt: str,
    tool_definitions: tuple[ToolDefinition, ...],
) -> GenerationRequest:
    return GenerationRequest(
        messages=[
            LLMMessage(role=MessageRole.SYSTEM, content=_base_system_instruction()),
            LLMMessage(role=MessageRole.USER, content=prompt),
        ],
        tools=list(tool_definitions),
        temperature=0.0,
        max_tokens=256,
    )


def _structured_request(prompt: str) -> GenerationRequest:
    return GenerationRequest(
        messages=[
            LLMMessage(
                role=MessageRole.SYSTEM,
                content=(
                    "Return only an object that satisfies the supplied JSON schema. "
                    "Do not call tools or add extra fields."
                ),
            ),
            LLMMessage(role=MessageRole.USER, content=prompt),
        ],
        temperature=0.0,
        max_tokens=160,
    )


def _ollama_tools(definitions: tuple[ToolDefinition, ...]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": definition.name,
                "description": definition.description,
                "parameters": definition.input_schema,
            },
        }
        for definition in definitions
    ]


def _safe_error(error: BaseException) -> dict[str, str]:
    if isinstance(error, LLMProviderError):
        return {"type": type(error).__name__, "message": str(error)}
    return {"type": type(error).__name__, "message": "evaluation request failed"}


def _call_latency(call: Any) -> tuple[Any, float, dict[str, str] | None]:
    started = time.perf_counter()
    try:
        return call(), (time.perf_counter() - started) * 1000, None
    except BaseException as error:  # noqa: BLE001 - runner records failures safely
        return None, (time.perf_counter() - started) * 1000, _safe_error(error)


def _grade_tool_selection(
    *,
    expected_tool: ToolExpectation,
    required_argument_keys: list[str],
    tool_calls: list[Mapping[str, Any]],
    registry: ToolRegistry,
) -> dict[str, Any]:
    selected = [str(call.get("name")) for call in tool_calls]
    arguments = [call.get("arguments") for call in tool_calls]
    result: dict[str, Any] = {
        "expected_tool": expected_tool,
        "selected_tools": selected,
        "arguments": arguments,
        "selection_correct": False,
        "arguments_valid": False,
        "failure_reason": None,
    }

    if expected_tool is None:
        if not selected:
            result["selection_correct"] = True
            result["arguments_valid"] = True
        else:
            result["failure_reason"] = "unexpected_tool"
        return result

    if not selected:
        result["failure_reason"] = "assistant_only_or_no_tool"
        return result
    if selected != [expected_tool]:
        result["failure_reason"] = "unexpected_tool_or_multiple_tools"
        return result

    result["selection_correct"] = True
    raw_arguments = arguments[0]
    if not isinstance(raw_arguments, Mapping):
        result["failure_reason"] = "arguments_not_an_object"
        return result

    try:
        registry.get(expected_tool).validate_arguments(raw_arguments)
    except Exception:  # noqa: BLE001 - tool validation is reported as a result
        result["failure_reason"] = "tool_schema_validation_failed"
        return result

    actual_keys = set(raw_arguments)
    if not set(required_argument_keys).issubset(actual_keys):
        result["failure_reason"] = "required_argument_missing"
        return result

    result["arguments_valid"] = True
    return result


def _tool_calls_from_provider(response: Any) -> list[dict[str, Any]]:
    return [
        {"name": call.name, "arguments": call.arguments, "call_id": call.call_id}
        for call in response.tool_calls
    ]


def _tool_cases(
    service: LLMService,
    cases: list[dict[str, Any]],
    definitions: tuple[ToolDefinition, ...],
    registry: ToolRegistry,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in cases:
        response, latency_ms, error = _call_latency(
            lambda: service.generate(_request_for_prompt(case["prompt"], definitions))
        )
        result: dict[str, Any] = {
            "id": case["id"],
            "language": case["language"],
            "prompt": case["prompt"],
            "latency_ms": round(latency_ms, 2),
            "expected_tool": case.get("expected_tool"),
            "selected_tools": [],
            "arguments": [],
            "arguments_valid": False,
            "selection_correct": False,
            "assistant_content": None,
            "failure_reason": None,
        }
        if error is not None:
            result["failure_reason"] = "provider_error"
            result["error"] = error
            results.append(result)
            continue

        tool_calls = _tool_calls_from_provider(response)
        graded = _grade_tool_selection(
            expected_tool=case.get("expected_tool"),
            required_argument_keys=case.get("required_argument_keys", []),
            tool_calls=tool_calls,
            registry=registry,
        )
        result.update(graded)
        result["assistant_content"] = response.content[:500] if response.content else None
        result["model"] = response.model
        result["finish_reason"] = response.finish_reason
        results.append(result)
    return results


def _structured_cases(
    service: LLMService,
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in cases:
        value, latency_ms, error = _call_latency(
            lambda: service.generate_structured(
                _structured_request(case["prompt"]), StructuredEvaluation
            )
        )
        result: dict[str, Any] = {
            "id": case["id"],
            "language": case["language"],
            "prompt": case["prompt"],
            "latency_ms": round(latency_ms, 2),
            "valid": error is None,
            "semantic_match": False,
            "failure_reason": None,
        }
        if error is not None:
            result["failure_reason"] = error["type"]
            result["error"] = error
        else:
            payload = value.model_dump(mode="json")
            result["value"] = payload
            result["semantic_match"] = (
                payload["language"] == case["expected_language"]
                and payload["topic"] == case["expected_topic"]
            )
            if not result["semantic_match"]:
                result["failure_reason"] = "semantic_expectation_mismatch"
        results.append(result)
    return results


def _runtime_metrics(payload: Mapping[str, Any]) -> dict[str, Any]:
    metric_keys = (
        "total_duration",
        "load_duration",
        "prompt_eval_count",
        "prompt_eval_cached_count",
        "prompt_eval_duration",
        "eval_count",
        "eval_duration",
    )
    metrics = {key: payload[key] for key in metric_keys if key in payload}
    eval_count = payload.get("eval_count")
    eval_duration = payload.get("eval_duration")
    if isinstance(eval_count, (int, float)) and isinstance(eval_duration, (int, float)):
        if eval_duration > 0:
            metrics["generation_tokens_per_second"] = round(
                eval_count / (eval_duration / 1_000_000_000), 2
            )
    for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            metrics[f"{key}_ms"] = round(value / 1_000_000, 2)
    return metrics


def _raw_chat(
    client: httpx.Client,
    settings: Settings,
    *,
    messages: list[dict[str, str]],
    definitions: tuple[ToolDefinition, ...] = (),
    options: dict[str, Any] | None = None,
    think: Any = _DEFAULT_THINK,
) -> tuple[dict[str, Any] | None, float, dict[str, str] | None]:
    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": False,
    }
    if definitions:
        payload["tools"] = _ollama_tools(definitions)
    if options:
        payload["options"] = options
    if think is not _DEFAULT_THINK:
        payload["think"] = think

    started = time.perf_counter()
    try:
        response = client.post(
            f"{settings.llm_base_url.rstrip('/')}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        parsed = response.json()
        if not isinstance(parsed, dict):
            raise ValueError("response object expected")
        return parsed, (time.perf_counter() - started) * 1000, None
    except BaseException as error:  # noqa: BLE001 - eval-only safe result
        return None, (time.perf_counter() - started) * 1000, _safe_error(error)


def _raw_tool_calls(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    message = payload.get("message")
    if not isinstance(message, Mapping):
        return []
    raw_calls = message.get("tool_calls", [])
    if not isinstance(raw_calls, list):
        return []
    calls: list[dict[str, Any]] = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, Mapping):
            continue
        function = raw_call.get("function")
        if not isinstance(function, Mapping):
            continue
        calls.append(
            {
                "name": function.get("name"),
                "arguments": function.get("arguments"),
                "call_id": raw_call.get("id"),
            }
        )
    return calls


def _raw_selection_result(
    *,
    payload: Mapping[str, Any] | None,
    case: dict[str, Any],
    latency_ms: float,
    error: dict[str, str] | None,
    registry: ToolRegistry,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": case["id"],
        "expected_tool": case.get("expected_tool"),
        "latency_ms": round(latency_ms, 2),
        "thinking": None,
        "selected_tools": [],
        "arguments": [],
        "selection_correct": False,
        "arguments_valid": False,
        "failure_reason": None,
    }
    if error is not None:
        result["failure_reason"] = "provider_error"
        result["error"] = error
        return result
    assert payload is not None
    message = payload.get("message")
    if isinstance(message, Mapping):
        result["thinking"] = bool(message.get("thinking"))
        result["assistant_content"] = message.get("content")
    graded = _grade_tool_selection(
        expected_tool=case.get("expected_tool"),
        required_argument_keys=case.get("required_argument_keys", []),
        tool_calls=_raw_tool_calls(payload),
        registry=registry,
    )
    result.update(graded)
    result["runtime_metrics"] = _runtime_metrics(payload)
    result["model"] = payload.get("model")
    result["finish_reason"] = payload.get("done_reason")
    return result


def _context_probes(
    client: httpx.Client,
    settings: Settings,
) -> list[dict[str, Any]]:
    results = []
    for context_size in (8192, 16384):
        payload, latency_ms, error = _raw_chat(
            client,
            settings,
            messages=[
                {
                    "role": "user",
                    "content": "Reply with exactly one word: ready",
                }
            ],
            options={"num_ctx": context_size, "temperature": 0},
            think=False,
        )
        results.append(
            {
                "context_size": context_size,
                "success": error is None,
                "latency_ms": round(latency_ms, 2),
                "runtime_metrics": _runtime_metrics(payload or {}),
                "error": error,
            }
        )
    return results


def _thinking_metadata(client: httpx.Client, settings: Settings) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.post(
            f"{settings.llm_base_url.rstrip('/')}/api/show",
            json={"model": settings.llm_model},
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "success": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "thinking": payload.get("thinking") if isinstance(payload, dict) else None,
        }
    except BaseException as error:  # noqa: BLE001 - eval-only safe result
        return {
            "success": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": _safe_error(error),
        }


def _thinking_probes(
    client: httpx.Client,
    settings: Settings,
    cases: list[dict[str, Any]],
    definitions: tuple[ToolDefinition, ...],
    registry: ToolRegistry,
) -> dict[str, Any]:
    modes: tuple[tuple[str, Any], ...] = (
        ("disabled", False),
        ("enabled", True),
        ("default", _DEFAULT_THINK),
    )
    results: list[dict[str, Any]] = []
    for case in cases:
        for mode_name, think in modes:
            payload, latency_ms, error = _raw_chat(
                client,
                settings,
                messages=[
                    {"role": "system", "content": _base_system_instruction()},
                    {"role": "user", "content": case["prompt"]},
                ],
                definitions=definitions,
                options={"temperature": 0, "num_predict": 256},
                think=think,
            )
            item = _raw_selection_result(
                payload=payload,
                case=case,
                latency_ms=latency_ms,
                error=error,
                registry=registry,
            )
            item["mode"] = mode_name
            results.append(item)
    return {
        "model_metadata": _thinking_metadata(client, settings),
        "results": results,
    }


def _command_probe(command: list[str]) -> dict[str, Any]:
    executable = shutil.which(command[0])
    if executable is None:
        return {"available": False, "output": None, "error": "command_unavailable"}
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "output": None, "error": "command_failed"}
    output = (completed.stdout or completed.stderr).strip()
    return {
        "available": completed.returncode == 0,
        "output": output[:2000] if output else None,
        "returncode": completed.returncode,
    }


def _latency_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        value
        for result in results
        for value in [result.get("latency_ms")]
        if isinstance(value, (int, float)) and math.isfinite(value)
    ]
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "total_ms": round(sum(values), 2),
        "mean_ms": round(sum(values) / len(values), 2),
        "min_ms": round(min(values), 2),
        "max_ms": round(max(values), 2),
    }


def run(cases_path: Path) -> dict[str, Any]:
    cases = _load_cases(cases_path)
    settings = get_settings()
    registry = _tool_registry_for_definitions()
    definitions = registry.definitions
    tool_names = [definition.name for definition in definitions]

    service, client = _make_service(settings)
    try:
        connectivity_response, connectivity_latency, connectivity_error = _call_latency(
            lambda: service.generate(
                GenerationRequest(
                    messages=[
                        LLMMessage(
                            role=MessageRole.USER,
                            content="Reply with exactly one word: ready",
                        )
                    ],
                    temperature=0.0,
                    max_tokens=16,
                )
            )
        )
        connection_success = connectivity_error is None
        result: dict[str, Any] = {
            "model_configured": settings.llm_model,
            "base_url_configured": settings.llm_base_url,
            "tool_names": tool_names,
            "tool_definitions": [definition.model_dump(mode="json") for definition in definitions],
            "connectivity": {
                "success": connection_success,
                "latency_ms": round(connectivity_latency, 2),
                "model_returned": getattr(connectivity_response, "model", None),
                "load_success": connection_success
                and bool(getattr(connectivity_response, "model", None)),
                "error": connectivity_error,
            },
            "hardware": {
                "ollama_ps": _command_probe(["ollama", "ps"]),
                "nvidia_smi": _command_probe(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                        "--format=csv,noheader,nounits",
                    ]
                ),
            },
            "context_sizes_tested": [8192, 16384],
            "thinking_modes_tested": ["disabled", "enabled", "default"],
        }

        if not connection_success:
            reason = "LIVE_MODEL_UNAVAILABLE"
            result["status"] = "BLOCKED"
            result["blocker"] = reason
            result["tool_selection"] = {
                "results": [
                    {
                        "id": case["id"],
                        "expected_tool": case.get("expected_tool"),
                        "failure_reason": reason,
                    }
                    for case in cases.get("tool_selection_cases", [])
                ],
                "latency": {"count": 0},
            }
            result["structured_json"] = {
                "results": [
                    {"id": case["id"], "valid": False, "failure_reason": reason}
                    for case in cases.get("structured_cases", [])
                ],
                "latency": {"count": 0},
            }
            result["context_probes"] = []
            result["thinking"] = {"results": [], "model_metadata": None}
            return result

        tool_results = _tool_cases(
            service,
            cases.get("tool_selection_cases", []),
            definitions,
            registry,
        )
        structured_results = _structured_cases(service, cases.get("structured_cases", []))
        context_results = _context_probes(client, settings)
        thinking_results = _thinking_probes(
            client,
            settings,
            cases.get("thinking_cases", []),
            definitions,
            registry,
        )

        tool_successes = sum(
            result["selection_correct"] and result["arguments_valid"]
            for result in tool_results
        )
        structured_successes = sum(result["valid"] for result in structured_results)
        failures = [
            result
            for result in tool_results
            if not (result["selection_correct"] and result["arguments_valid"])
        ] + [result for result in structured_results if not result["valid"]]
        result["status"] = "PASS" if not failures else "PARTIALLY_PASSED"
        result["tool_selection"] = {
            "results": tool_results,
            "success_count": tool_successes,
            "total_count": len(tool_results),
            "valid_argument_count": sum(result["arguments_valid"] for result in tool_results),
            "latency": _latency_summary(tool_results),
        }
        result["structured_json"] = {
            "results": structured_results,
            "success_count": structured_successes,
            "total_count": len(structured_results),
            "semantic_match_count": sum(
                result["semantic_match"] for result in structured_results
            ),
            "latency": _latency_summary(structured_results),
        }
        result["context_probes"] = context_results
        result["thinking"] = thinking_results
        result["failures"] = failures
        return result
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("cases.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run(args.cases)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result.get("status") == "PASS" else 2 if result.get("status") == "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
