# Agent 1 Structure - Profiling Agent

**Role:** Agent 1 (Profiling) from `api-structure-en.md` section 1.3 - interviews the user, builds their profile, and creates/maintains Building Blocks during the conversation.

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

Agent 1 runs as its own HTTP microservice - the `agents/profiler_agent` package (matching the `agents/` convention used by Agents 2-5) - called **synchronously**, with no streaming and no retry: `apps/api/src/api/agent_client.py::get_agent_reply()` issues `POST {PROFILER_AGENT_URL}/reply` and blocks until it responds. Any failure (timeout, connection error, non-2xx status) raises and surfaces as a 500 to the API Server's own caller - no silent recovery or degraded continuation.

**Why a separate service instead of running in-process inside `apps/api`:** consistency with how Agents 2-5 are packaged and deployed, independent scaling/restarts from the API server, and the service needs no DB credentials at all - it only ever returns data for the API Server to persist (Section 1).

**Current gap:** `GET /health` exists (see Section 3) for a future k8s readiness/liveness probe, but no k8s Deployment manifest exists yet for this service.

---

## 3. Wire Contract

Single-shot request/response. Agent 1 never fetches anything on its own mid-turn (no tool-calling back into the API Server) - the API Server pre-loads everything Agent 1 could need for that turn and sends it in one request. This keeps the service simple and stateless with predictable latency: one network hop per turn, no nested round trips inside a synchronous, non-streaming call.

**Payload philosophy: send generously, not minimally.** Since there's no second chance to ask for more mid-turn, under-including a field is a real failure mode (the agent silently doesn't know something), while over-including one is free - the API Server already has the full row loaded from the DB. So `context.job` carries the **entire job record** (plus the company it belongs to), not a hand-picked subset. A field only gets dropped later if it turns out to be genuinely unused by the prompts, based on real usage - never guessed away up front.

**Endpoint:** `POST /reply` (plus `GET /health` for the k8s probe noted in Section 2).

### Request

```json
{
  "conversation_id": "conv-3",
  "conversation_type": "application_edit",
  "user_id": "u-1",
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
| `user_id` | present (tracing only) | present (tracing only) | present (tracing only) |
| `building_block_id` | `null` | the block being reworded | the block being replaced for this application |
| `application_id` | `null` | `null` | the application this variant is for |
| `context.existing_building_blocks` | full list of the user's blocks | `null` | `null` |
| `context.target_building_block` | `null` | the block's current content | the block's current content |
| `context.job` | `null` | `null` | the full job record + company (above) |

`job`'s field list mirrors `Job.to_dict()` in `apps/api/src/api/models.py`, plus a nested `company` object (id/name/website), minus pure audit timestamps (`discovered_at`/`updated_at`) - those are bookkeeping, not job content, and are the one deliberate exclusion from "send everything."

**Irrelevant `context` keys are always present, set to `null` - never omitted.** Every request carries all four `context.*` keys (and `building_block_id`/`application_id`) regardless of `conversation_type`; only their value differs (populated vs. `null`). This gives a single, fixed request shape across all three types (one example teaches the whole contract, no need to compare three payloads to learn the full field list), and keeps "not relevant to this type" (explicit `null`) distinguishable from "a bug forgot to set it" (a key that should exist but doesn't). This deliberately differs from `building_blocks_created` omitting `id` entirely (Response section below) - that's a different situation: the value there cannot exist yet (no row has been inserted), whereas a `context` field always conceptually exists, it's just empty for this turn.

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

**Why `created` entries never carry an `id`:** `building_blocks.id` is assigned client-side by the API Server (`default=uuid.uuid4` on the SQLAlchemy model, not a DB-generated column) - Agent 1 never touches that model, so it cannot know an id for a row that doesn't exist yet. `updated` entries, by contrast, reference a row that already exists, so the id is already known and must be echoed back. The API Server treats a mismatched `id` in `building_blocks_updated` (not equal to the request's `building_block_id`) as a bug and fails loudly (`abort(500)`, logged as an error) rather than accepting it silently.

### Response (failure)

Non-2xx, e.g. `500`:
```json
{ "error": "string" }
```
No message is persisted by the API Server in this case.

---

## 4. Internal Memory

Agent 1 keeps its own private state between turns of the same conversation, via a LangGraph **checkpointer** (`SqliteSaver`) keyed by `conversation_id`, backed by a SQLite file Agent 1 owns exclusively (`profiler_agent/config.py::Config.CHECKPOINT_DB_PATH`, default `profiler_agent_state.sqlite3` inside `agents/profiler_agent/`) - not the platform's shared Postgres DB from `001_user_schema.sql`/`002_company_schema.sql`.

**What it stores:** conversation-progress state only - a running `summary`, the current interview `phase`, and `phase_streak` (Section 5). It **never** stores building blocks, job data, or anything covered by `context` in Section 3 - those always come fresh from the API Server's request, since the shared DB (not Agent 1's private memory) is the single source of truth for them. This avoids a dual-source-of-truth drift risk: if a block is edited through a different path (e.g. a separate `refinement` conversation, or a direct `PATCH /building-blocks/:id`) while this `profiling` conversation is ongoing, Agent 1 must never be working off a stale private copy of that block.

**Why `message_history` still carries the full transcript in every request (Section 3 doesn't shrink):** it's a resilience fallback, not the primary mechanism. When a valid checkpoint exists for the conversation, Agent 1 uses its own compact internal state instead of reprocessing the full history - this is what actually solves the token/latency growth problem in a long-running `profiling` conversation. When no checkpoint exists (or it was lost - e.g. a redeploy, or the private store's data was reset), Agent 1 falls back to reconstructing its state directly from the full `message_history` it was sent anyway. The API Server's request shape doesn't need to know or care which case applies - it always sends the same payload.

**Scope note:** this mostly matters for `profiling` (the long conversation). `refinement`/`application_edit` are short, narrowly-scoped conversations (a handful of turns) where reprocessing the full history every time is cheap regardless - the checkpointer's efficiency benefit is real but small there.

---

## 5. Conversation Flow (`profiling`)

Each interview phase gets its own LangGraph node with its own narrow, phase-specific system prompt (`prompts.py`), rather than one prompt covering every topic - this keeps each call focused on exactly one job.

**What's not a rigid state machine:** *within* a phase, the node's own LLM call decides everything a skilled interviewer would - what to ask next, when enough detail exists, when to draft bullet variants, when the topic is exhausted. *Between* phases, moving on (or not) is likewise the node's own judgment call, described in each phase's prompt; nothing in `graph.py` decides that a topic is "done" under normal operation (the one exception is the stuck-loop breaker described below). The only thing code decides is *which* node/prompt applies to the current turn - based on `conversation_type` and the agent's own previously-reported `phase`.

**Graph shape:**

```
                                   ┌─ intro_node ────────────┐
                                   ├─ background_node ───────┤
load_state → route_turn (by        ├─ skills_node ───────────┤
  conversation_type + phase)  ──→  ├─ education_node ────────┼──→ END
                                   ├─ projects_node ─────────┤
                                   ├─ summary_confirm_node ──┤
                                   └─ other_node ────────────┘
```

- `load_state` - reads the checkpoint (Section 4) for this `conversation_id`: `{ phase, summary, phase_streak }`. Falls back to reconstructing from the full `message_history` if no checkpoint exists yet or it was lost.
- `route_turn` - a conditional edge, not an LLM call. `conversation_type != "profiling"` → `other_node` (refinement/application_edit, single prompt, no phases). Otherwise: `user_message == ""` → `intro_node` (the one-time kickoff signal, per Section 3); else dispatch on the agent's own last-reported `phase` to the matching node, defaulting to `background_node` for a stale/lost/unrecognized phase (a safe re-entry point, since the kickoff has clearly already happened if `user_message` is non-empty).
- Each phase node (`intro_node`/`background_node`/`skills_node`/`education_node`/`projects_node`/`summary_confirm_node`) runs the same shared LLM-call body (`_run_llm_turn` in `graph.py`) with that phase's own dedicated system prompt. Input: `summary`, current `phase`, `context.existing_building_blocks`, `user_message`, `message_history`. Output (structured): `{ reply, phase, summary, building_blocks_created, building_blocks_updated, drafted_variants }`.

The updated `{ phase, summary, phase_streak }` isn't written back explicitly by any node - LangGraph's checkpointer snapshots the full state automatically after every node runs, so it's already persisted by the time the node returns. Nothing here reaches the wire contract (Section 3) either way - these fields are internal only, the API Server never sees them.

**`phase` values** (each maps to one node + one building-block category; the agent self-reports which applies next - `route_turn` reads that value to pick the next node):

| Phase | Node | Roughly covers | Building block category |
|---|---|---|---|
| `intro` | `intro_node` | first turn only (kickoff), agent introduces itself | none |
| `background` | `background_node` | free-form background/experience overview | `about_user` (simple fact - no variants, no confirmation turn) |
| `skills` | `skills_node` | programming languages, tools, technologies | `technical_skills` (simple fact - no variants, no confirmation turn) |
| `education` | `education_node` | degrees, certifications, formal training | `education` (simple fact - no variants, no confirmation turn) |
| `projects` | `projects_node` | project-by-project STAR-driven questioning | `project` (achievement narrative - 3 bullet variants drafted, created only after a later confirming turn) |
| `summary_and_confirm` | `summary_confirm_node` | role synthesis, final review, wrap-up | `role` (achievement narrative - same 3-variant/confirm flow as `project`) |

No code enforces moving forward through this list in order - the agent can report the same phase again, or an earlier one (e.g. user adds a project after reaching `summary_and_confirm`), and `route_turn` will happily send the next turn back to that phase's node. That's expected, not an error.

**Guards inside `_run_llm_turn` (`graph.py`), applied on top of the node's own LLM call:**
- **Legal-phase clamp:** each node has a fixed set of `phase` values it's allowed to output next (`_LEGAL_OUTGOING_PHASES`) - e.g. `projects_node` may only report `projects` or `summary_and_confirm`. An out-of-set value is clamped back to the incoming phase (stay put), never redirected to some other guessed phase.
- **Pending-draft clamp:** `projects`/`summary_and_confirm` are draft-then-confirm phases - a turn that just presented a fresh, not-yet-confirmed bullet draft (`drafted_variants` non-empty, nothing created yet) is not allowed to also advance `phase` in the same turn, since that would route the user's next (confirming) message to the wrong node and silently orphan the achievement.
- **Stuck-loop breaker:** if a phase makes zero progress (`phase` unchanged **and** no blocks created/updated) for `_MAX_STUCK_TURNS` (5) consecutive turns, code forces the next phase from a fixed fallback order (`_PHASE_SEQUENCE`), regardless of what the LLM decided. This is deliberately progress-on-phase-change-only, not "or created any blocks" - a stuck node could otherwise keep emitting spurious blocks turn after turn without ever advancing, masking the very loop this guard exists to catch. This is the one exception to "code never decides a topic is done": it only fires as a last resort after several turns of measurable non-progress.

**Scope:** this section applies to `profiling` only. `refinement`/`application_edit` don't use `phase`/per-phase nodes at all - they're already narrowly scoped from the start via `building_block_id`/`application_id` in the request, so there's no multi-step interview to track; both route to the single `other_node`.
