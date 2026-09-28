# Local LLM live evaluation

This is an explicit, non-CI evaluation area for the configured Ollama model.
It does not execute academic tools and it does not change the normal pytest
suite.

## Run

From the repository root, after the backend image is available:

```powershell
docker compose run --rm --no-deps `
  -w /app -e PYTHONPATH=/app `
  -v "${PWD}/evals/llm:/evals/llm" `
  backend python /evals/llm/live_eval.py `
  --output /evals/llm/results.json
```

The runner uses the configured `LLM_BASE_URL`, `LLM_MODEL`, and
`LLM_TIMEOUT_SECONDS`. If Ollama is on the host rather than reachable at the
configured URL from the container, set `LLM_BASE_URL` to the reachable address
for the command; no tunnel, firewall, or public exposure is configured by this
runner.

The target model is `qwen3.5:9b-q4_K_M`. The runner reports
`LIVE_MODEL_UNAVAILABLE` and exits with status 2 when the model host cannot be
reached, rather than fabricating results.

## What is measured

The ordinary English, Arabic, mixed-language, structured-output, and tool
selection cases use the production path:

`LLMService -> OllamaProvider -> /api/chat`

Tool selection exposes only the current three definitions:

- `check_course_eligibility`
- `degree_audit`
- `search_official_documents`

Selected tools are not executed. Argument validity is checked against the
existing tool schemas only.

The context-size (`8192`, `16384`) and thinking (`disabled`, `enabled`, and
model `default`) probes are evaluation-only direct HTTP calls. They are kept
outside production contracts because the application provider currently uses
non-streaming generation and intentionally has no context/thinking controls.
They record Ollama runtime metadata when the server returns it, including load
duration, prompt/evaluation counts and durations, and generation tokens/sec.

The runner also attempts `ollama ps` and `nvidia-smi` in its execution
environment. Host GPU measurements may need to be collected separately when
the runner is inside the backend container.

Ollama API references:

- <https://docs.ollama.com/api/chat>
- <https://docs.ollama.com/capabilities/thinking>
