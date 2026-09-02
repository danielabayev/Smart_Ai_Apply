# Database Tables

Reference for the tables defined in `apps/api/src/api/models.py`, which mirrors
the SQL migrations in this directory (the migrations remain the single source
of truth for the actual schema; this file documents what the ORM models
currently declare).

## `users`
A platform user.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK, default `uuid.uuid4` |
| `full_name` | VARCHAR(255) | NOT NULL |
| `email` | VARCHAR(255) | NOT NULL, UNIQUE |
| `phone_number` | VARCHAR(50) | nullable |
| `linkedin_url` | VARCHAR(512) | nullable |
| `github_url` | VARCHAR(512) | nullable |
| `created_at` | DATETIME | NOT NULL, server default `now()` |
| `updated_at` | DATETIME | NOT NULL, server default `now()` |

## `user_preferences`
1:1 job-search preferences per user.

| Column | Type | Notes |
|---|---|---|
| `user_id` | UUID | PK, FK → `users.id` (CASCADE) |
| `match_threshold` | SMALLINT | NOT NULL, default 70 |
| `min_salary` | NUMERIC(12,2) | nullable |
| `salary_currency` | VARCHAR(3) | default `"ILS"` |
| `include_jobs_without_salary` | BOOLEAN | NOT NULL, default `True` |
| `location` | VARCHAR(255) | nullable |
| `work_arrangement` | ENUM(`remote`,`hybrid`,`onsite`) | nullable |
| `employment_types` | ARRAY(TEXT) | NOT NULL, default `[]` |
| `created_at` | DATETIME | NOT NULL, server default `now()` |
| `updated_at` | DATETIME | NOT NULL, server default `now()` |

## `conversations`
A chat thread with Agent 1 (profiling / refinement / application_edit).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK, default `uuid.uuid4` |
| `user_id` | UUID | NOT NULL, FK → `users.id` (CASCADE) |
| `type` | ENUM(`profiling`,`refinement`,`application_edit`) | NOT NULL, default `"profiling"` |
| `building_block_id` | UUID | nullable, FK → `building_blocks.id` (CASCADE) |
| `application_id` | UUID | nullable, FK → `applications.id` (CASCADE) |
| `status` | ENUM(`active`,`finished`) | NOT NULL, default `"active"` |
| `created_at` | DATETIME | NOT NULL, server default `now()` |
| `updated_at` | DATETIME | NOT NULL, server default `now()` |

## `messages`
A single turn within a conversation.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK, default `uuid.uuid4` |
| `conversation_id` | UUID | NOT NULL, FK → `conversations.id` (CASCADE) |
| `sender` | ENUM(`user`,`agent`) | NOT NULL |
| `content` | TEXT | NOT NULL |
| `model_used` | VARCHAR(100) | nullable |
| `response_time_ms` | INTEGER | nullable |
| `created_at` | DATETIME | NOT NULL, server default `now()` |

## `building_blocks`
A reusable resume content piece (project, skill, education, ...).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK, default `uuid.uuid4` |
| `user_id` | UUID | NOT NULL, FK → `users.id` (CASCADE) |
| `conversation_id` | UUID | NOT NULL, FK → `conversations.id` (CASCADE) |
| `category` | ENUM(`project`,`technical_skills`,`education`,`about_user`,`role`) | NOT NULL |
| `title` | VARCHAR(255) | NOT NULL |
| `content` | TEXT | NOT NULL |
| `variants` | JSONB | NOT NULL, default `[]` |
| `created_at` | DATETIME | NOT NULL, server default `now()` |
| `updated_at` | DATETIME | NOT NULL, server default `now()` |

## `applications`
A tailored-resume application pending user approval.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK, default `uuid.uuid4` |
| `user_id` | UUID | NOT NULL, FK → `users.id` (CASCADE) |
| `job_id` | BIGINT | NOT NULL (no FK declared in the model) |
| `match_score` | SMALLINT | NOT NULL |
| `status` | ENUM(`pending_tailoring`,`pending_approval`,`approved`,`rejected`) | NOT NULL, default `"pending_tailoring"` |
| `document_content` | TEXT | nullable |
| `created_at` | DATETIME | NOT NULL, server default `now()` |
| `updated_at` | DATETIME | NOT NULL, server default `now()` |

## `application_building_blocks`
Many-to-many join: which building blocks were used in an application.

| Column | Type | Notes |
|---|---|---|
| `application_id` | UUID | PK (composite), FK → `applications.id` (CASCADE) |
| `building_block_id` | UUID | PK (composite), FK → `building_blocks.id` (CASCADE) |

## `companies`
A discovered employer, written by Agent 2 (Discovery).

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT | PK |
| `name` | VARCHAR(255) | NOT NULL |
| `website` | VARCHAR(512) | NOT NULL |
| `status` | ENUM(`active`,`flagged_for_review`) | NOT NULL, default `"active"` |
| `last_checked_at` | DATETIME | nullable |
| `last_job_found_at` | DATETIME | nullable |
| `created_at` | DATETIME | NOT NULL, server default `now()` |
| `updated_at` | DATETIME | NOT NULL, server default `now()` |

## `jobs`
An extracted job posting, written by Agent 3 (Extractor). `id` is a
sequential BIGINT (not a UUID) so Agent 4 can scan jobs in order using a
simple per-user cursor (see `user_job_scan_cursor`).

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT | PK |
| `company_id` | BIGINT | NOT NULL, FK → `companies.id` (CASCADE) |
| `title` | VARCHAR(255) | NOT NULL |
| `description` | TEXT | NOT NULL |
| `requirements` | ARRAY(TEXT) | NOT NULL, default `[]` |
| `source_url` | VARCHAR(1024) | NOT NULL |
| `salary_min` | NUMERIC(12,2) | nullable |
| `salary_max` | NUMERIC(12,2) | nullable |
| `salary_currency` | VARCHAR(3) | nullable |
| `employment_type` | ENUM(`full_time`,`part_time`,`contract`) | nullable |
| `work_arrangement` | ENUM(`remote`,`hybrid`,`onsite`) | nullable |
| `location` | VARCHAR(255) | nullable |
| `discovered_at` | DATETIME | NOT NULL, server default `now()` |
| `updated_at` | DATETIME | NOT NULL, server default `now()` |

## `user_job_scan_cursor`
Agent 4's per-user scan-progress cursor. A 1:1 extension table keyed
directly on `user_id` rather than a column on `users`, since it's written
on every building-block/preference change and read by a separate agent
unrelated to user identity.

| Column | Type | Notes |
|---|---|---|
| `user_id` | UUID | PK, FK → `users.id` (CASCADE) |
| `last_checked_job_id` | BIGINT | NOT NULL, default 0 |
| `updated_at` | DATETIME | NOT NULL, server default `now()` |
