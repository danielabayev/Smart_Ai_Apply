#!/bin/sh
# Explicitly runs the migration files in the required order (user schema
# before company schema - see api&schema/migrations-README.md), instead of
# relying on the entrypoint's alphabetical filename sort. Sourced by the
# official postgres image's docker-entrypoint.sh on first container start
# against an empty data volume; POSTGRES_USER/POSTGRES_DB are already
# exported at that point.
set -eu

echo "Running migration 1/2: 001_user_schema.sql"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /migrations/001_user_schema.sql

echo "Running migration 2/2: 002_company_schema.sql"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /migrations/002_company_schema.sql

echo "Migrations complete."
