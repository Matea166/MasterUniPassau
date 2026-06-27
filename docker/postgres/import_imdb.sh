#!/usr/bin/env bash
set -euo pipefail

IMDB_URL="https://bonsai.cedardb.com/job/imdb.tgz"

APP_IMDB_DIR="/workspace/imdb_data"
APP_ARCHIVE="$APP_IMDB_DIR/imdb.tgz"
APP_EXTRACT_DIR="$APP_IMDB_DIR/extracted"

DB_IMDB_DIR="/imdb_data"

DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
DB_NAME="imdb"

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

SCHEMA_FILE="/workspace/docker/postgres/imdb/schema.sql"
LOAD_FILE=$(find "$APP_EXTRACT_DIR" -type f -name "load.sql" | head -1)

if [ ! -f "$SCHEMA_FILE" ]; then
    echo "Error: schema.sql not found at $SCHEMA_FILE"
    exit 1
fi

if [ -z "$LOAD_FILE" ]; then
echo "Error: load.sql not found after extraction."
exit 1
fi

PATCHED_LOAD_FILE="$APP_IMDB_DIR/load_docker.sql"

echo "--- Found import files ---"
echo "Schema file: $SCHEMA_FILE"
echo "Load file:   $LOAD_FILE"
echo ""

echo "--- Preparing Docker-compatible load file ---"
python - <<PY
from pathlib import Path
import re

app_imdb_dir = Path("$APP_IMDB_DIR").resolve()
db_imdb_dir = "$DB_IMDB_DIR"

load_file = Path("$LOAD_FILE")
patched_file = Path("$PATCHED_LOAD_FILE")

text = load_file.read_text()

# Build a mapping from every extracted data filename to the path visible

# inside the PostgreSQL container.

data_files = {}
for path in app_imdb_dir.rglob("*"):
if path.is_file():
rel = path.relative_to(app_imdb_dir)
data_files[path.name] = f"{db_imdb_dir}/{rel.as_posix()}"

def replace_copy_path(match):
prefix = match.group(1)
old_path = match.group(2)
suffix = match.group(3)

```
filename = Path(old_path).name

if filename in data_files:
    return f"{prefix}{data_files[filename]}{suffix}"

return match.group(0)
```

# Replace COPY ... FROM 'some/path/file.csv' with the equivalent

# PostgreSQL-container path under /imdb_data.

text = re.sub(
r"(FROM\s+['\"])([^'\"]+)(['\"])",
replace_copy_path,
text,
flags=re.IGNORECASE,
)

patched_file.write_text(text)
PY

echo "--- Checking PostgreSQL connection ---"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "SELECT 1;" > /dev/null

echo "--- Recreating database '$DB_NAME' ---"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres 
-c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME';"

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres 
-c "DROP DATABASE IF EXISTS $DB_NAME;"

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres 
-c "CREATE DATABASE $DB_NAME;"

echo "--- Importing schema ---"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$SCHEMA_FILE"

echo "--- Importing data ---"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$PATCHED_LOAD_FILE"

echo "--- Running ANALYZE ---"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "ANALYZE;"

echo "--- Import complete. Available tables: ---"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "\dt"
