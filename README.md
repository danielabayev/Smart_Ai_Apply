# Smart_Ai_Apply
Create resume, find jobs, apply.

## Docker Compose

[docker-compose.yml](docker-compose.yml) defines the local Postgres database (`db` service,
`postgres:16-alpine`) used by `apps/api`. On first start against an empty volume it also runs
the SQL migrations under `api&schema/` in a fixed order via [docker/init-db.sh](docker/init-db.sh).

```bash
docker compose up -d db
```

The `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` values in the file are a **fixed, non-secret
dev-only default** (`smart_ai_apply`/`smart_ai_apply`/`smart_ai_apply`) - fine for local
development, but must be overridden (e.g. via a real secret store) before this is ever deployed
anywhere reachable outside your machine.

For the full local run sequence (Ollama, profiler-agent, API server, verification steps), see
[start_program.MD](start_program.MD).

TODO:
1) after the project is completed in the buisness side add authentication
and authorization and implement proper API documentation.
2) check prompt and SQL injection.
- [ ] No auth currently on the API — add before any real deployment or external access.
- [ ] DEBUG logs (stdout) capture raw user input + extracted entities tied to user_id.
      If this handles real PII/career data, revisit: avoid logging full free-text verbatim,
      decide where logs are persisted/rotated, and who can access them.
- [ ] Error handling currently halts the entire program on any failure — fine for dev,
      but reconsider for production (graceful degradation / partial recovery?).
3) check the message send by the user, if the message is long then X words check it more carrfully.
4) Add logic prevent update the cursor update while conversation keep going, the target is to prevent agent 4 keep evaluate the jobs after every new building block.
5) Check what happend if the user want more then 3 variants?
- [ ] Before deploying (k8s): move all env vars currently loaded from local `.env`/`docker-compose.yml`
      defaults (`GOOGLE_API_KEY`, `POSTGRES_PASSWORD`/`DATABASE_URL`, and any others) into proper
      k8s `Secret`/`ConfigMap` resources - the current hardcoded dev-only defaults (see the
      Docker Compose section above) must not carry over as-is.
also need to check which way will be most fit to share the variants number to all of the projects/code files.