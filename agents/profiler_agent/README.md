# Profiler Agent (Agent 1 - Profiling)

Standalone HTTP microservice implementing the "Career Mining Agent" described in
`Initial_prompt.txt`, following the invocation model decided in `agent-structure-en.md`
(separate service, called synchronously by the API server - see `apps/api`).

## Run

```bash
uv sync
uv run profiler-agent
```

Uses Google Gemini via the Google AI Studio API - set `GOOGLE_API_KEY` (get one at
https://aistudio.google.com/apikey) before starting the service.

Environment variables:

- `GOOGLE_API_KEY` (required) - Google AI Studio API key used to authenticate with Gemini.
- `PROFILER_AGENT_PORT` (default `8001`)
- `PROFILER_AGENT_MODEL` (default `gemini-3.6-flash`) - any Gemini model name that supports
  structured/tool output.
- `PROFILER_AGENT_MODEL_TEMPERATURE` (default `0.4`) - ignored when `PROFILER_AGENT_MODEL` is one
  of the fixed-sampling models (currently `gemini-3.6-flash`, the default, and
  `gemini-3.5-flash-lite`) - Google removed custom sampling controls on those; see
  `_FIXED_SAMPLING_MODELS` in `llm.py`.
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


TODO:
1) worth check if in projects/summary node need to add save of future ask and check if there some data saved fot future ask (as the agent shouldnt ask about 2/3 things in parallal and if the user say he worked on 3 projects we might need this).
2) need to add time for the education part (in prompt?).

