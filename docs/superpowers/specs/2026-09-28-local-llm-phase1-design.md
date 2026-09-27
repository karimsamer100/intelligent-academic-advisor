# Local LLM Phase 1 Foundation — Milestone 1

## Purpose

Introduce the minimal provider-neutral internal LLM boundary for the backend.
The foundation will let later local-runtime adapters and academic tool
wrappers change independently while preserving the existing deterministic
Planning Engine and RAG boundaries.

Ollama is the selected future local runtime and Qwen3.5-9B is the selected
target model, but Milestone 1 does not integrate either one. No
Ollama-specific code, configuration, SDK, HTTP call, model download, or
runtime behavior belongs here.

## Boundaries

The application flow is:

```text
caller -> app.services.llm_service.LLMService -> app.llm.interface.LLMProvider
```

`LLMService` owns only application-level delegation. It does not contain
academic logic, retrieval logic, conversation history, orchestration loops,
persistence, API routes, or provider-specific error translation. Planning and
RAG code remain unchanged.

The provider interface is the only dependency that a future local-runtime
adapter must implement. No LLM SDK or runtime-specific type may cross that
interface.

## Public contracts

`app.llm.contracts` will define strict Pydantic contracts:

- `MessageRole`: `system`, `user`, `assistant`, and `tool`.
- `LLMMessage`: role, optional content for assistant tool-call messages,
  provider-neutral tool calls for assistant messages, and an optional tool
  call id for tool messages.
- `ToolDefinition`: stable name, description, and a JSON-Schema-compatible
  `input_schema` mapping. It will not expose a provider-specific tool shape.
- `ToolCall`: optional call id, tool name, and structured argument mapping.
- `GenerationRequest`: non-empty messages, optional tool definitions, and only
  the minimal shared controls `temperature` and `max_tokens`.
- `GenerationResponse`: assistant content and/or tool calls, optional finish
  reason, and optional returned model identifier.

Unknown fields will be rejected at these boundaries. Content and tool
contracts will reject invalid empty values and `GenerationRequest` will reject
duplicate tool definitions by name where those invariants are meaningful.

## Provider interface and structured output

`LLMProvider` will be a replaceable provider protocol with:

```python
generate(request: GenerationRequest) -> GenerationResponse
```

Milestone 1 does not define `generate_structured`. Structured JSON parsing and
Pydantic response validation belong to Milestone 2, alongside the real Ollama
provider. Runtime-specific structured-output optimizations must remain behind
the provider boundary.

## Error model

`app.llm.errors` will define internal LLM-layer exceptions for:

- provider unavailable / connection failure;
- provider timeout;
- provider execution failure;
- invalid provider response.

These are safe provider-domain categories. A future `OllamaProvider` will
translate HTTP, network, and runtime-specific exceptions into them. `LLMService`
will not inspect, catch, or reinterpret transport/runtime exceptions; it will
propagate provider-domain errors unchanged.

## Testing

Focused unit tests will use only local fake `LLMProvider` subclasses. They will
cover:

- provider replacement and dependency isolation;
- normal `LLMService` delegation;
- message and generation request validation;
- tool definition/call validation;
- text-only, tool-call-only, and combined generation responses;
- provider-domain error propagation without service-side transport mapping.

The existing backend, Planning, and RAG suites will be run unchanged after the
focused tests. No GPU, model, internet access, or LLM server will be needed.

## Explicitly deferred

- OllamaProvider integration and Qwen3.5-9B runtime configuration.
- Any other model/runtime or remote networking.
- Structured JSON output and `generate_structured` (Milestone 2).
- `ToolResult`, `ToolError`, tool execution, and concrete Planning/RAG tool
  wrappers (Milestone 3/orchestration as appropriate).
- Unknown tool-call handling (Milestone 3/orchestration as appropriate).
- Conversation history, session/profile persistence, and orchestration loops.
- LLM API routes and API-level error mapping.
