# Migrations - Run Order

Run the files **in the numeric order of their filenames**:

1. `001_user_schema.sql` - User Schema (users, preferences, conversations, messages, building_blocks (incl. `variants` JSONB for Agent 1's 3 stored angle variants per block), applications)
2. `002_company_schema.sql` - Company Schema (companies, jobs, user_job_scan_cursor)

## Why the order is critical

`002_company_schema.sql` **depends** on `001_user_schema.sql` having already run, because it:
- Reuses the `work_arrangement_type` ENUM defined in 001, instead of duplicating it.
- Reuses the `set_updated_at()` function defined in 001 (for the triggers).
- Creates a real FK from `user_job_scan_cursor.user_id` to `users.id` (a table from 001).

Running `002_company_schema.sql` before `001_user_schema.sql` will fail.
