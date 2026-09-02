# Agent 1 Structure - Profiling Agent

> **Status:** Draft in progress (built section by section)
> **Role:** Agent 1 (Profiling) from `api-structure-en.md` section 1.3 - interviews the user, builds their profile, and creates/maintains Building Blocks during the conversation.

---

## 1. Role & Scope

Agent 1 is a single agent that owns every `conversations` row, regardless of `type`. It does not branch into separate graphs per type - the same flow runs every time; only the system prompt and the context loaded before that prompt change based on `conversation_type`.

| `type` | Reference fields | Context loaded | Behavior | Output |
|---|---|---|---|---|
| `profiling` | none | user's existing `building_blocks` (if reopened) | run/continue the interview | `building_blocks_created` as each project/skill/etc. is gathered |
| `refinement` | `building_block_id` | that one block | reword it **in place** | `building_blocks_updated` (same block id) |
| `application_edit` | `application_id` + `building_block_id` (the block being replaced, pre-selected in the UI) | that block's content + the job it's being tailored for | create a job-specific **variant**, original untouched | `building_blocks_created` (the new variant, never `updated`) |

**Why `application_edit` creates instead of updates:** a CV is assembled entirely from building blocks (`application_building_blocks`), not free text. Rewording a line for one job would corrupt that block everywhere else it's used (in the block list, and in any other application it's linked to). So Agent 1 always creates a new variant block for `application_edit`, and never touches `document_content` directly.

**Where Agent 1's responsibility ends, for `application_edit`:** once Agent 1 hands back the new variant block, Agent 1 is done - it never writes to the DB (the API Server is the sole writer). Two things still need to happen outside Agent 1:
1. The API Server swaps the link in `application_building_blocks` for that application: drop the old `building_block_id`, add the new variant's id.
2. Agent 5 (Tailoring) is re-triggered to re-render `document_content` from the application's updated set of blocks.

Both of these are downstream of Agent 1's output, not something Agent 1 does itself - flagged here so the boundary is explicit, full mechanics belong in `api-structure-en.md` / Agent 5's doc.

---

## 2. Invocation Model

**Decision:** Agent 1 is a separate HTTP microservice - its own `agents/profiler_agent` package (matching the `agents/` convention already used by Agents 2-5), deployed as its own k8s Deployment, called **synchronously** by the API Server. No streaming for now.

`apps/api/src/api/agent_client.py::get_agent_reply()` is replaced with an internal HTTP call, e.g. `POST http://profiler-agent/reply`, carrying the same fields the stub function already takes/returns today (`conversation_id`, `conversation_type`, `message_history`, `user_message` in; `reply`, `building_blocks_created`, `building_blocks_updated` out) - the exact wire shape is worth its own section next. The API Server waits for the response before returning from `POST /conversations/:id/messages` - unchanged from today's "no streaming" behavior.

**Why this over running in-process inside `apps/api`:** consistency with how Agents 2-5 are packaged and deployed, independent scaling/restarts from the API server, and the service needs no DB credentials at all - it only ever returns data for the API Server to persist (Section 1).

**Follow-up decisions this creates** (not resolved yet, tracked in Open Points below): timeout/retry policy for when the service is slow or down, and readiness/liveness probes for the k8s Deployment.

---

## 3. Wire Contract

**Decision:** single-shot request/response. Agent 1 never fetches anything on its own mid-turn (no tool-calling back into the API Server) - the API Server pre-loads everything Agent 1 could need for that turn and sends it in one request. This trades flexibility for a simpler, stateless service with predictable latency (one network hop per turn, no nested round trips inside a synchronous, non-streaming call).

**Payload philosophy: send generously, not minimally.** Since there's no second chance to ask for more mid-turn, under-including a field is a real failure mode (the agent silently doesn't know something), while over-including one is free - the API Server already has the full row loaded from the DB. So `context.job` carries the **entire job record** (plus the company it belongs to), not a hand-picked subset. If a field turns out to be genuinely unused by the prompts, it gets dropped later based on real usage - not guessed away up front.

**Endpoint:** `POST /reply` (plus `GET /health` for the k8s readiness/liveness probe noted above - not detailed here).

### Request

```json
{
  "conversation_id": "conv-3",
  "conversation_type": "application_edit",
  "message_history": [
    { "sender": "user", "content": "...", "created_at": "..." }
  ],
  "user_message": "Emphasize the experience with high loads more",
  "building_block_id": "b2",
  "application_id": "app-99",
  "context": {
    "existing_building_blocks": null,
    "target_building_block": {
      "id": "b2",
      "category": "project",
      "title": "E-commerce Platform",
      "content": "Built a full e-commerce system with Python and Django, handling 10,000 users per day"
    },
    "job": {
      "id": 501,
      "title": "Senior Backend Engineer",
      "description": "Looking for a backend developer with experience in large-scale systems",
      "requirements": ["distributed systems", "high scale", "Python"],
      "source_url": "https://company-x.com/careers/501",
      "salary_min": 30000,
      "salary_max": 42000,
      "salary_currency": "ILS",
      "employment_type": "full_time",
      "work_arrangement": "hybrid",
      "location": "Tel Aviv",
      "company": {
        "id": 12,
        "name": "Company X",
        "website": "https://company-x.com"
      }
    }
  }
}
```

Fields present per type (per the Section 1 table):

| Field | `profiling` | `refinement` | `application_edit` |
|---|---|---|---|
| `building_block_id` | `null` | the block being reworded | the block being replaced for this application |
| `application_id` | `null` | `null` | the application this variant is for |
| `context.existing_building_blocks` | full list of the user's blocks | `null` | `null` |
| `context.target_building_block` | `null` | the block's current content | the block's current content |
| `context.job` | `null` | `null` | the full job record + company (above) |

`job`'s field list mirrors `Job.to_dict()` in `apps/api/src/api/models.py`, plus a nested `company` object (id/name/website), minus pure audit timestamps (`discovered_at`/`updated_at`) - those are bookkeeping, not job content, and are the one deliberate exclusion from "send everything."

**Decision: irrelevant `context` keys are always present, set to `null` - never omitted.** Every request carries all four `context.*` keys (and `building_block_id`/`application_id`) regardless of `conversation_type`; only their value differs (populated vs. `null`). This gives a single, fixed request shape across all three types (one example teaches the whole contract, no need to compare three payloads to learn the full field list), and keeps "not relevant to this type" (explicit `null`) distinguishable from "a bug forgot to set it" (a key that should exist but doesn't). This deliberately differs from `building_blocks_created` omitting `id` entirely (Response section below) - that's a different situation: the value there cannot exist yet (no row has been inserted), whereas a `context` field always conceptually exists, it's just empty for this turn.

### Response (success)

```json
{
  "reply": "string",
  "building_blocks_created": [ { "category": "...", "title": "...", "content": "..." } ],
  "building_blocks_updated": [ { "id": "...", "category": "...", "title": "...", "content": "..." } ]
}
```

- `profiling` → only `building_blocks_created` is ever populated (no `id` - not assigned yet, see below).
- `refinement` → only `building_blocks_updated`, exactly one entry, `id` equal to the request's `building_block_id`.
- `application_edit` → only `building_blocks_created`, exactly one entry (the variant) - no `id`, and no explicit link back to the block it replaces; the API Server already has that pairing from the request it sent (`building_block_id` + `application_id`), so nothing extra is needed here.

**Why `created` entries never carry an `id`:** `building_blocks.id` is assigned client-side by the API Server (`default=uuid.uuid4` on the SQLAlchemy model, not a DB-generated column) - Agent 1 never touches that model, so it cannot know an id for a row that doesn't exist yet. `updated` entries, by contrast, reference a row that already exists, so the id is already known and must be echoed back. The API Server should treat a mismatched `id` in `building_blocks_updated` (not equal to the request's `building_block_id`) as a bug and fail loudly (logged as an error) rather than accept it silently - exact logging conventions are still to be defined in a later section.

### Response (failure)

Non-2xx, e.g. `500`:
```json
{ "error": "string" }
```
No message is persisted by the API Server in this case.

---

## 4. Internal Memory

**Decision:** Agent 1 keeps its own private state between turns of the same conversation, via a LangGraph **checkpointer** - keyed by `conversation_id`, backed by a small datastore Agent 1 owns exclusively (a separate, private store - not the platform's shared Postgres DB from `001_user_schema.sql`/`002_company_schema.sql`; concrete technology - Redis/Postgres/SQLite - not decided yet).

**What it stores:** conversation-progress state only - e.g. a running summary and/or the current interview phase (see Section 5). It **never** stores building blocks, job data, or anything covered by `context` in Section 3 - those always come fresh from the API Server's request, since the shared DB (not Agent 1's private memory) is the single source of truth for them. This avoids a dual-source-of-truth drift risk: if a block is edited through a different path (e.g. a separate `refinement` conversation, or a direct `PATCH /building-blocks/:id`) while this `profiling` conversation is ongoing, Agent 1 must never be working off a stale private copy of that block.

**Why `message_history` still carries the full transcript in every request (Section 3 doesn't shrink):** it's a resilience fallback, not the primary mechanism. When a valid checkpoint exists for the conversation, Agent 1 uses its own compact internal state instead of reprocessing the full history - this is what actually solves the token/latency growth problem in a long-running `profiling` conversation. When no checkpoint exists (or it was lost - e.g. a redeploy, or the private store's data was reset), Agent 1 falls back to reconstructing its state directly from the full `message_history` it was sent anyway. The API Server's request shape doesn't need to know or care which case applies - it always sends the same payload.

**Scope note:** this mostly matters for `profiling` (the long conversation). `refinement`/`application_edit` are short, narrowly-scoped conversations (a handful of turns) where reprocessing the full history every time is cheap regardless - the checkpointer's efficiency benefit is real but small there.

---

## 5. Conversation Flow (`profiling`)

**Decision:** no rigid state machine. One system prompt drives the whole interview; the LLM decides what to ask next based on the checkpoint's summary + `context.existing_building_blocks`, the same way a skilled interviewer would, rather than following a hard-coded step order. On top of that, the same LLM call also reports back a `phase` label each turn - purely for tracking and to keep the prompt focused, never to enforce order. This is a middle ground between a fully scripted flow and a fully unstructured one.

**Graph shape** (deliberately thin, since C doesn't need per-phase nodes):

```
load_state → generate
```

- `load_state` - reads the checkpoint (Section 4) for this `conversation_id`: `{ phase, summary }`. Falls back to reconstructing from the full `message_history` if no checkpoint exists yet or it was lost.
- `generate` - the single LLM call. Input: summary/history, current `phase`, `context.existing_building_blocks`, `user_message`. Output (structured): `{ reply, phase, building_blocks_created }`.

The updated `{ phase, summary }` isn't written back explicitly by either node - LangGraph's checkpointer snapshots the full state automatically after every node runs, so it's already persisted by the time `generate` returns. An earlier `persist_state` node existed for this but did no persistence of its own (nothing it needed to do wasn't already handled by the checkpointer); it was dropped and its one trace log line moved into `generate`. Nothing here reaches the wire contract (Section 3) either way - `phase`/`summary` are internal only, the API Server never sees them.

**Proposed `phase` values** (draft - a label the LLM assigns itself, not a code-enforced sequence):

| Phase | Roughly covers | Building blocks typically created here |
|---|---|---|
| `intro` | first turn only, agent introduces itself | none |
| `background` | free-form background/experience overview | `about_user` |
| `skills_and_education` | programming languages, general skills, education | `technical_skills`, `education` |
| `projects` | project-by-project questioning | `project` (one per project, as it's ready) |
| `summary_and_confirm` | role synthesis, final review, polishing, confirmation | `role`, then updates only |

No code enforces moving forward through this list in order - the LLM can report the same phase again, or an earlier one (e.g. user adds a project after reaching `summary_and_confirm`), and that's expected, not an error. The `phase` value's only jobs are: (1) let the next turn's prompt be more focused ("you're currently in the projects phase"), and (2) give us visibility in logs into how a given interview is progressing.

**Scope:** this section applies to `profiling` only. `refinement`/`application_edit` don't use `phase` at all - they're already narrowly scoped from the start via `building_block_id`/`application_id` in the request, so there's no multi-step interview to track.
