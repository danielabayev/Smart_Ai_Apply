# How to Run & Check the System

Quick-start for running everything locally. For deep DB/Docker troubleshooting see
[process/docker-db-api-setup.md](process/docker-db-api-setup.md).

> **Keep this file up to date** - whenever a run step, port, env var, or service changes,
> update this doc in the same change.

## Components

| Component | What it is | Port |
|---|---|---|
| `db` | Postgres (Docker) | 5432 |
| Ollama | Local LLM runtime, serves `llama3.1:8b` | 11434 |
| `agents/profiler_agent` | Agent 1 (Profiling) - LangGraph microservice | 8001 |
| `apps/api` | Flask API server + chat frontend | 5000 |

## 1. Start the database (Docker Desktop must be running first)

```bash
cd /c/projects/Smart_Ai_Apply && docker compose up -d db
```

Check it's healthy:
```bash
docker ps --filter name=smart-ai-apply-db --format "{{.Names}}: {{.Status}}"
```

**Migrations ([docker/init-db.sh](docker/init-db.sh))**: on a brand-new volume, the container
auto-runs `001_user_schema.sql` → `002_company_schema.sql`
in that hardcoded order (see the mounts in [docker-compose.yml](docker-compose.yml)). Confirm with:
```bash
docker compose logs db | grep -i migration
```
Expect `Running migration 1/2` ... `Running migration 2/2` ... `Migrations complete.`

⚠️ **This only happens once, against an empty volume.** If you already have a running dev DB
from before a migration file existed, `init-db.sh` will **not** retroactively apply it - you must
either apply the new `.sql` file by hand:
```bash
docker cp "api&schema/00X_your_migration.sql" smart-ai-apply-db:/tmp/
docker exec smart-ai-apply-db psql -v ON_ERROR_STOP=1 -U smart_ai_apply -d smart_ai_apply -f /tmp/00X_your_migration.sql
```
or wipe and recreate the volume (⚠️ **deletes all local data**, dev only):
```bash
docker compose down -v && docker compose up -d db
```
(On git-bash/MSYS, prefix `docker exec`/`docker cp` commands using absolute-looking paths like
`/tmp/...` with `MSYS_NO_PATHCONV=1` - otherwise the shell mangles them into a Windows path.)

## 2. Make sure Ollama is up with the model pulled

```bash
curl -s http://localhost:11434/api/tags
```
Should list `llama3.1:8b`. If missing:
```bash
ollama pull llama3.1:8b
```

## 3. Start the profiler-agent microservice (own terminal - it blocks)

```bash
cd /c/projects/Smart_Ai_Apply/agents/profiler_agent && uv run profiler-agent
```
Check: `curl http://localhost:8001/health` → `{"service":"profiler-agent","status":"ok"}`

Env vars (all optional, see [agents/profiler_agent/README.md](agents/profiler_agent/README.md)):
`PROFILER_AGENT_PORT`, `PROFILER_AGENT_MODEL` (default `llama3.1:8b`), `OLLAMA_BASE_URL`
(default `http://localhost:11434`), `PROFILER_AGENT_CHECKPOINT_DB`.

## 4. Start the API server (second terminal)

```bash
cd /c/projects/Smart_Ai_Apply/apps/api && uv run flask --app api.app:create_app run --debug
```
Check: `curl http://localhost:5000/health` → `{"service":"api","status":"ok"}`

`PROFILER_AGENT_URL` defaults to `http://localhost:8001` - only set it if the agent runs on a
different host/port.

## 5. Use it

Open **http://localhost:5000/** in a browser - the chat UI. It auto-creates a `profiling`
conversation on first load. Each reply currently takes **30-60+ seconds** (local 8B model on
CPU/GPU, not a hosted API) - this is expected, not a hang.

## 6. Verify what happened, beyond the UI

- **Logs**: the profiler-agent terminal prints the structured `log_event` DEBUG trace
  (`INPUT_PROCESSING` → `FACT_EXTRACTION`/`ANGLE_SYNTHESIS` → `DB_PAYLOAD_PREP`) for every turn;
  the API terminal shows the HTTP request/response and any error.
- **DB contents**:
```bash
docker exec smart-ai-apply-db psql -U smart_ai_apply -d smart_ai_apply -c "SELECT sender, content FROM messages ORDER BY created_at;"
```
```bash
docker exec smart-ai-apply-db psql -U smart_ai_apply -d smart_ai_apply -c "SELECT title, category, content, variants FROM building_blocks;"
```

## Stopping

```bash
docker compose stop
```
Stop the `profiler-agent` and `flask run` terminals with Ctrl+C. Data persists in the
`smart_ai_apply_db_data` volume.
