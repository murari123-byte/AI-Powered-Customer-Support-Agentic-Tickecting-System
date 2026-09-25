#!/bin/sh
# Runs once, when the postgres_data volume is first created.
# Creates an empty database for pytest, so tests never touch development data.
# Tables are NOT created here: Alembic migrations create them in every database.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE DATABASE "$TEST_POSTGRES_DB" OWNER "$POSTGRES_USER";
SQL
