# Profiler Agent (Agent 1 - Profiling)

Standalone HTTP microservice implementing the "Career Mining Agent" described in
`Initial_prompt.txt`, following the invocation model decided in `agent-structure-en.md`
(separate service, called synchronously by the API server - see `apps/api`).

## Run

```bash
uv sync
uv run profiler-agent
```

Uses a local Ollama model - make sure `ollama serve` is running and the model tag below has been
pulled (`ollama pull llama3.1:8b`).

Environment variables (all optional):

- `PROFILER_AGENT_PORT` (default `8001`)
- `PROFILER_AGENT_MODEL` (default `llama3.1:8b`) - any local Ollama model tag; must support tool
  calling for structured output (`ollama list` shows `tools` under capabilities).
- `OLLAMA_BASE_URL` (default `http://localhost:11434`)
- `PROFILER_AGENT_CHECKPOINT_DB` (default `profiler_agent_state.sqlite3` in this directory) -
  private conversation-state store (LangGraph checkpointer), never the shared platform DB.

## Endpoints

- `POST /reply` - single-shot conversation turn. See `agent-structure-en.md` section 3 for the
  request/response wire contract.
- `GET /health` - liveness/readiness probe.

## Scope note

This package only talks to the API server via the `/reply` request/response contract - it has no
credentials for, and never connects to, the shared Postgres database (`api&schema/`). All DB writes
happen in `apps/api` after it receives this service's response.
