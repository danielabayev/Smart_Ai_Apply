# Docker + Postgres + API Setup

Full process for standing up the local database and running the
unified API service (`apps/api`), from a machine with nothing
installed yet.

Related files:
- [docker-compose.yml](../docker-compose.yml) - defines the `db` (Postgres) service
- [docker/init-db.sh](../docker/init-db.sh) - explicitly runs the two migration files in order (not filename-sort dependent)
- [api&schema/](../api&schema/) - SQL migrations + API structure docs
- [apps/api](../apps/api) - the Flask service

---

## Phase 0 - Install Docker Desktop

1. Download and install: https://www.docker.com/products/docker-desktop/
2. Launch it, wait for the tray icon to say "Docker Desktop is running."

Verify:
```bash
docker --version
```
```bash
docker compose version
```

## Phase 1 - Start Postgres (with explicit, ordered migrations)

Run from the **repo root** (same folder as `docker-compose.yml`):
```bash
docker compose up -d
```

This pulls `postgres:16-alpine` if needed, starts the container, and -
only on this first start against an empty volume - sources
`docker/init-db.sh`. That script explicitly runs `001_user_schema.sql`
then `002_company_schema.sql` by hardcoded path, so migration order
doesn't depend on filenames sorting correctly.

## Phase 2 - Verify the container and migrations

```bash
docker compose ps
```
Expect `db` with status `Up` / `healthy` (may take a few seconds to
flip to healthy).

```bash
docker compose logs db
```
Look for, in this exact order:
```
Running migration 1/2: 001_user_schema.sql
... CREATE TYPE / CREATE TABLE ...
Running migration 2/2: 002_company_schema.sql
... CREATE TYPE / CREATE TABLE ...
Migrations complete.
```
If either `psql` call fails, the script's `set -eu` stops it
immediately and the error surfaces here - no silent partial migration.

## Phase 3 - Verify the schema directly

```bash
docker exec smart-ai-apply-db psql -U smart_ai_apply -d smart_ai_apply -c "\dt"
```
Expect 10 tables: `users`, `user_preferences`, `conversations`,
`messages`, `building_blocks`, `applications`,
`application_building_blocks`, `companies`, `jobs`,
`user_job_scan_cursor`.

## Phase 4 - Run the API service

```bash
cd apps/api
uv run flask --app api.app:create_app run --port 8000
```
Leave it running in its own terminal. No env vars are needed if you
used the credentials/port baked into `docker-compose.yml` -
`apps/api/src/api/config.py` defaults to that same connection string.

## Phase 5 - Verify the service end to end

In another terminal:
```bash
curl http://127.0.0.1:8000/health
```
Expect `{"service":"api","status":"ok"}`.

```bash
curl http://127.0.0.1:8000/api/v1/users/me
```
Expect a JSON user object - this confirms Flask successfully reached
Postgres and read the migrated schema (the first call auto-seeds a
single mocked user, since auth is mocked for this MVP).

---

## Stopping / restarting

```bash
docker compose stop
```
```bash
docker compose start
```
Data persists in the `smart_ai_apply_db_data` named volume across
stop/start.

## Re-running migrations (e.g. after editing the SQL files)

The init script only runs once, against an empty volume. To force it
to run again:
```bash
docker compose down -v
```
⚠️ This deletes all data in the volume. Then repeat Phase 1.

## Troubleshooting

- **`docker: command not found` / `error during connect`** - Docker
  Desktop isn't running yet. Open it and wait for the tray icon to say
  "running."
- **Port 5432 already in use** - a local Postgres install is likely
  already using it. Either stop it, or change the host port in
  `docker-compose.yml` (`"5433:5432"`) and update `DATABASE_URL`
  accordingly (`...@localhost:5433/...`).
- **`curl` to `localhost` hangs instead of failing fast** - try
  `127.0.0.1` explicitly; some Windows setups resolve `localhost` to
  IPv6 first, which can stall before falling back to IPv4.
- **Migration errors about types/functions already existing** - you
  likely ran migrations twice against the same volume. Use
  `docker compose down -v` and start over rather than re-running
  against a partially-migrated DB.
