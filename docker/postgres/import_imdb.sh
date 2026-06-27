#!/usr/bin/env bash
set -euo pipefail

IMDB_URL="https://bonsai.cedardb.com/job/imdb.tgz"

APP_IMDB_DIR="/workspace/imdb_data"
APP_ARCHIVE="$APP_IMDB_DIR/imdb.tgz"
APP_EXTRACT_DIR="$APP_IMDB_DIR/extracted"

DB_IMDB_DIR="/imdb_data"
DB_EXTRACT_DIR="$DB_IMDB_DIR/extracted"

DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
DB_NAME="imdb"

SCHEMA_FILE="/workspace/docker/postgres/imdb/schema.sql"

export PGPASSWORD="$DB_PASSWORD"

echo "==========================================="
echo "        Optional IMDB / JOB Import         "
echo "==========================================="
echo "Target database: $DB_NAME"
echo "Download URL:     $IMDB_URL"
echo "Local data dir:   $APP_IMDB_DIR"
echo ""

mkdir -p "$APP_IMDB_DIR"
mkdir -p "$APP_EXTRACT_DIR"

if [ ! -f "$APP_ARCHIVE" ]; then
echo "--- Downloading IMDB archive ---"
wget "$IMDB_URL" --no-check-certificate -O "$APP_ARCHIVE"
else
echo "--- Archive already exists, skipping download ---"
echo "$APP_ARCHIVE"
fi

if [ -z "$(find "$APP_EXTRACT_DIR" -mindepth 1 -print -quit)" ]; then
echo "--- Extracting IMDB archive ---"
tar -xzf "$APP_ARCHIVE" -C "$APP_EXTRACT_DIR"
else
echo "--- Extracted files already exist, skipping extraction ---"
fi

if [ ! -f "$SCHEMA_FILE" ]; then
echo "Error: schema.sql not found at $SCHEMA_FILE"
exit 1
fi

echo "--- Checking PostgreSQL connection ---"
psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "SELECT 1;" > /dev/null

echo "--- Recreating database '$DB_NAME' ---"
psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME';"
psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"
psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME;"

echo "--- Importing schema ---"
psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$SCHEMA_FILE"

echo "--- Disabling foreign-key triggers during bulk import ---"
psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
DO $$
DECLARE
r RECORD;
BEGIN
FOR r IN
SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname = 'public'
LOOP
EXECUTE format('ALTER TABLE %I.%I DISABLE TRIGGER ALL', r.schemaname, r.tablename);
END LOOP;
END
$$;
"

copy_table() {
local table_name="$1"
local app_csv_file="$APP_EXTRACT_DIR/${table_name}.csv"
local db_csv_file="$DB_EXTRACT_DIR/${table_name}.csv"

if [ ! -f "$app_csv_file" ]; then
    echo "Warning: CSV file not found for table '$table_name': $app_csv_file"
    return
fi

echo "--- Importing table: $table_name ---"

local first_line
first_line=$(head -n 1 "$app_csv_file")

if [[ "$first_line" == id,* ]]; then
    psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "COPY ${table_name} FROM '${db_csv_file}' WITH (FORMAT csv, HEADER true, NULL '', QUOTE '\"', ESCAPE E'\\\\');"
else
    psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "COPY ${table_name} FROM '${db_csv_file}' WITH (FORMAT csv, HEADER false, NULL '', QUOTE '\"', ESCAPE E'\\\\');"
fi

}

echo "--- Importing CSV data ---"

# Independent / lookup tables first

copy_table "comp_cast_type"
copy_table "company_type"
copy_table "info_type"
copy_table "kind_type"
copy_table "keyword"
copy_table "link_type"
copy_table "role_type"

# Entity tables

copy_table "char_name"
copy_table "company_name"
copy_table "name"
copy_table "title"

# Dependent tables

copy_table "aka_name"
copy_table "aka_title"
copy_table "cast_info"
copy_table "complete_cast"
copy_table "movie_companies"
copy_table "movie_info"
copy_table "movie_info_idx"
copy_table "movie_keyword"
copy_table "movie_link"
copy_table "person_info"

echo "--- Re-enabling triggers after bulk import ---"
psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
DO $$
DECLARE
r RECORD;
BEGIN
FOR r IN
SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname = 'public'
LOOP
EXECUTE format('ALTER TABLE %I.%I ENABLE TRIGGER ALL', r.schemaname, r.tablename);
END LOOP;
END
$$;
"

echo "--- Running ANALYZE ---"
psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "ANALYZE;"

echo "--- Import complete. Available tables: ---"
psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "\dt"

echo "--- Row counts ---"
psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT 'aka_name' AS table_name, COUNT(*) FROM aka_name
UNION ALL SELECT 'aka_title', COUNT(*) FROM aka_title
UNION ALL SELECT 'cast_info', COUNT(*) FROM cast_info
UNION ALL SELECT 'char_name', COUNT(*) FROM char_name
UNION ALL SELECT 'comp_cast_type', COUNT(*) FROM comp_cast_type
UNION ALL SELECT 'company_name', COUNT(*) FROM company_name
UNION ALL SELECT 'company_type', COUNT(*) FROM company_type
UNION ALL SELECT 'complete_cast', COUNT(*) FROM complete_cast
UNION ALL SELECT 'info_type', COUNT(*) FROM info_type
UNION ALL SELECT 'keyword', COUNT(*) FROM keyword
UNION ALL SELECT 'kind_type', COUNT(*) FROM kind_type
UNION ALL SELECT 'link_type', COUNT(*) FROM link_type
UNION ALL SELECT 'movie_companies', COUNT(*) FROM movie_companies
UNION ALL SELECT 'movie_info', COUNT(*) FROM movie_info
UNION ALL SELECT 'movie_info_idx', COUNT(*) FROM movie_info_idx
UNION ALL SELECT 'movie_keyword', COUNT(*) FROM movie_keyword
UNION ALL SELECT 'movie_link', COUNT(*) FROM movie_link
UNION ALL SELECT 'name', COUNT(*) FROM name
UNION ALL SELECT 'person_info', COUNT(*) FROM person_info
UNION ALL SELECT 'role_type', COUNT(*) FROM role_type
UNION ALL SELECT 'title', COUNT(*) FROM title;
"
