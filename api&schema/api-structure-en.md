# API Structure - Automated Resume-to-Job Matching Platform

> **Status:** Initial MVP
> **Base URL:** `/api/v1`
> **Architecture:** A single **API Server** (user-facing endpoints + company data endpoints + agent-internal endpoints, see `apps/api`), a future **Dispatch Service**, and a pipeline of 4 Agents (k8s CronJobs) connected via queues.

---

## High-Level Flow Diagram

```
User ←→ API Server ←→ Agents Pipeline
             ↑          (2→3→4→5, connected via queues)
             │
   Dispatch Service (future, not yet built)
```

---

## 1. User-Facing Endpoints

### 1.1 Auth *(Mocked for MVP)*
> Single fixed user, no real registration/login at this stage. Reserved for future expansion (Session / JWT / managed provider like Auth0).

### 1.2 Profile & Preferences

| Method | Path | Description |
|---|---|---|
| GET | `/users/me` | Get user details |
| PATCH | `/users/me` | Update user details |
| GET | `/users/me/preferences` | Get preferences (including `match_threshold` - minimum match percentage for a job) |
| PUT | `/users/me/preferences` | Update preferences |

### 1.3 Conversations with Agent 1 (Profiling)

> Agent 1 runs one long conversation with the user: introduces itself → user describes their background → agent confirms general details (programming languages, skills, education) → project-by-project questioning → building blocks are created *during* the conversation (not at the end) → final presentation, polishing, and confirmation.
>
> The user can also open additional conversations later (to add new experience), as well as short, focused conversations to re-word a specific block (`type: refinement`).

| Method | Path | Description |
|---|---|---|
| POST | `/conversations` | Start a new conversation (general, or focused with `type` + reference to a block/application) |
| GET | `/conversations` | List all of the user's conversations |
| GET | `/conversations/:id` | Specific conversation + message history + building blocks created in it |
| POST | `/conversations/:id/messages` | Send a message → returns agent reply (no streaming) + `building_blocks_created` + `building_blocks_updated` |
| POST | `/conversations/:id/finish` | Mark the conversation as finished by the user (status only, does not trigger generation) |

**Example response shape from `/conversations/:id/messages`:**
```json
{
  "agent_reply": "The agent's response text",
  "building_blocks_created": [ { "id": "...", "text": "..." } ],
  "building_blocks_updated": [ { "id": "...", "text": "..." } ]
}
```

### 1.4 Building Blocks

| Method | Path | Description |
|---|---|---|
| GET | `/building-blocks` | List all blocks (filterable by `conversation_id`) |
| GET | `/building-blocks/:id` | A specific block |
| PATCH | `/building-blocks/:id` | Direct text edit by the user |
| DELETE | `/building-blocks/:id` | Delete a block |
| POST | `/building-blocks/:id/regenerate` | Opens a short, focused conversation (`type: refinement`) to re-word the block, via the same `/conversations` endpoints |

### 1.5 Applications Pending Approval

> An "application" = a tailored resume only (no cover letter at this stage). The user sees the full document, can edit it directly **and** request a re-write via the agent. What happens after approval is still undecided (automatic dispatch or not), so this action stays flexible: for now it only marks a status.

| Method | Path | Description |
|---|---|---|
| GET | `/applications` | List applications (filter by `status`: `pending_tailoring` / `pending_approval` / `approved` / `rejected`) |
| GET | `/applications/:id` | Application details + tailored resume content |
| PATCH | `/applications/:id/document` | Direct text edit of the resume |
| POST | `/applications/:id/regenerate` | Focused conversation with the agent (`type: application_edit`) to re-word the resume |
| POST | `/applications/:id/approve` | Mark as approved *(what actually happens after approval - automatic or manual submission - is not yet decided)* |
| POST | `/applications/:id/reject` | Reject the match |
| GET | `/applications/:id/download` | Download the resume as a file (PDF/Word) - especially needed if there is no auto-dispatch |

### 1.6 Internal Endpoints (Agent-facing only)

> Not exposed to the end user - used by the Agents to communicate with the API Server.

| Method | Path | Caller | Description |
|---|---|---|---|
| POST | `/internal/applications` | Agent 4 (Evaluation) | Create a new Application when a match crosses the user's `match_threshold` (status: `pending_tailoring`) |
| PATCH | `/internal/applications/:id` | Agent 5 (Tailoring) | Update with the generated tailored resume (status → `pending_approval`) |

---

## 2. Company Data Endpoints

> Served by the same **API Server** as section 1. Actual dispatch/sending is deliberately kept separate (the future **Dispatch Service**, section 2.4) so agent write traffic and eventual dispatch traffic don't bottleneck each other.

### 2.1 Writes (by Agents 2-4, via internal HTTP)

| Method | Path | Agent | Description |
|---|---|---|---|
| POST | `/companies` | Agent 2 (Discovery) | Create/update a discovered company |
| PATCH | `/companies/:id` | Agent 2 | Update company details |
| POST | `/jobs` | Agent 3 (Extractor) | Create an extracted job (auto-assigned sequential `id`) |
| PATCH | `/jobs/:id` | Agent 3 | Update job details |

> **Note:** `companies.id` and `jobs.id` are sequential numbers (BIGINT), not UUIDs - this is what enables the scanning mechanism in section 2.3 below. All other tables in the system (users, applications, etc.) remain UUID.

### 2.2 Reads (by Frontend, directly)

| Method | Path | Description |
|---|---|---|
| GET | `/jobs` | List jobs (search/filter) |
| GET | `/jobs/:id` | Specific job details - called by the Frontend alongside Application details (two separate calls, not chained through each other) |
| GET | `/companies/:id` | Company details |

### 2.3 Match-Scanning Mechanism (Agent 4) - no endpoint, no matches table

Agent 4 does **not** write a match record for every check. Instead, each user has a "cursor" (`last_checked_job_id`) marking how far (by sequential job number) they've already been scanned. On each run:

1. Agent 4 fetches the user's current `last_checked_job_id`.
2. Scans `jobs` in ascending order starting from the next number, computing a match score against each.
3. If the score ≥ `match_threshold` → calls the API Server (`POST /internal/applications`).
4. Updates `last_checked_job_id` to the last job number checked.

**Resetting the cursor:** When the user's `user_preferences` or `building_blocks` change, the API Server resets `last_checked_job_id` back to 0, so previously-rejected jobs get re-checked against the new criteria.

> **Note:** The detailed requirements/met breakdown that makes up the score is still stored only in Agent 4's run logs (`GET /agents/evaluation/runs/:run_id/logs`), not in the DB.

### 2.4 Dispatch Service *(future skeleton)*

Does not yet exist as an HTTP service. When `POST /applications/:id/approve` is called on the API Server, an event is published to the `application-approved-queue`. Once the Dispatch Service is built, it will simply listen to that queue - without any changes needed to the API Server.

### 2.5 Internal Monitoring (Agents 2-5)

| Method | Path | Description |
|---|---|---|
| GET | `/agents/status` | Status of all agents (last run, success/failure, current queue backlog) |
| GET | `/agents/:name/status` | Status of a specific agent |
| GET | `/agents/:name/runs` | Run history (timestamps + status) |
| GET | `/agents/:name/runs/:run_id/logs` | Logs from a specific run - for debugging logic |

### 2.6 Internal Queues (Message Queue, not REST)

| Queue Name | Producer | Consumer |
|---|---|---|
| `company-discovery-queue` | Agent 2 (Discovery) | Agent 3 (Extractor) |
| `job-extraction-queue` | Agent 3 (Extractor) | Agent 4 (Evaluation) |
| `evaluation-queue` | Agent 4 (Evaluation) | Agent 5 (Tailoring) |
| `application-approved-queue` | API Server (on approve) | *(future)* Dispatch Service |

---

## 3. Application Creation Flow - Full Summary

1. **Agent 2 (Discovery)** finds relevant companies → writes to the API Server, publishes to `company-discovery-queue`.
2. **Agent 3 (Extractor)** extracts jobs from those companies → writes to the API Server, publishes to `job-extraction-queue`.
3. **Agent 4 (Evaluation)** scans jobs in ascending order starting from the user's cursor (`last_checked_job_id`), computing a match score for each:
   - **If the score ≥ the `match_threshold`** set by the user → calls the API Server (`POST /internal/applications`) to create a new Application (status: `pending_tailoring`), and publishes to `evaluation-queue`.
   - Either way, updates `last_checked_job_id` to the current job, so the next run continues from there.
   - The full requirements/met breakdown is stored in the run logs only, not in the DB.
4. **Agent 5 (Tailoring)** picks up tasks from `evaluation-queue`, generates a tailored resume, and updates the Application (`PATCH /internal/applications/:id`, status → `pending_approval`).
5. **The user** sees the application in `GET /applications`, edits/re-words it as needed, and approves it (`POST /applications/:id/approve`).
6. An `application.approved` event is published to `application-approved-queue`. The **future Dispatch Service** will listen to this queue once built. In the meantime - the user downloads the resume (`GET /applications/:id/download`) and submits it manually.

---

## Open Points for Future Discussion

1. **Real authentication** - not yet chosen (Session / JWT / managed provider). The current structure assumes a single fixed user.
2. **Automatic dispatch** - not yet decided whether it will be built at all; if so, an additional human-in-the-loop step, job-board ToS handling, and CAPTCHA/bot detection need to be planned.
3. **Scraping legality** - legal review needed to confirm that pulling data from external job sources is permitted.
4. **API Server scale** - currently a single service handling both user-facing and company data endpoints; if traffic grows (e.g. agent write volume bottlenecking user-facing reads), consider splitting back into separate services/deployments (they already speak REST to each other's data, so this is a deployment change, not a rewrite).
