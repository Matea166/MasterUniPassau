#!/usr/bin/env bash

# Chow-Liu baseline benchmark: runs a bnsl cardinality-estimation script and
# augments its output with PostgreSQL planner estimates.
#
# Non-interactive mode (used by scripts/run_*.sh): set both
#   BENCH_DB      PostgreSQL database to query for planner estimates
#   BENCH_SCRIPT  cardinality_estimation/cardinality_estimation_<dataset>.py
# to skip the menus. The CSV the Python script loads is selected via the
# CSV_FILE environment variable (see the script headers).

# Configuration

DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
RESULTS_DIR="card_results"

export PGPASSWORD="$DB_PASSWORD"

mkdir -p $RESULTS_DIR

echo "==========================================="
echo "   Cardinality Estimation Benchmarker      "
echo "==========================================="

# 1. FETCH DATABASES FROM POSTGRES

if [ -n "${BENCH_DB:-}" ]; then
selected_db="$BENCH_DB"
echo "Using database: $selected_db"
else
echo "--- Fetching available databases from PostgreSQL at $DB_HOST:$DB_PORT ---"
db_list=($(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -t -A -c "SELECT datname FROM pg_database WHERE datistemplate = false AND datname <> 'postgres' ORDER BY datname;"))

if [ ${#db_list[@]} -eq 0 ]; then
echo "Error: Could not find any non-default databases in PostgreSQL at $DB_HOST:$DB_PORT."
exit 1
fi

echo "Select the database to use for comparisons:"
select selected_db in "${db_list[@]}"; do
if [ -n "$selected_db" ]; then
echo "Using database: $selected_db"
break
else
echo "Invalid selection."
fi
done
fi

# 2. FIND PYTHON FILES

# 2. FIND PYTHON FILES

if [ -n "${BENCH_SCRIPT:-}" ]; then
if [ ! -f "$BENCH_SCRIPT" ]; then
echo "Error: BENCH_SCRIPT not found: $BENCH_SCRIPT"
exit 1
fi
target_files=("$BENCH_SCRIPT")
else
files=(cardinality_estimation/cardinality_estimation_*.py)
if [ ${#files[@]} -eq 0 ]; then
echo "No cardinality_estimation_*.py files found."
exit 1
fi

echo -e "\nSelect a Python script to run:"
select file in "${files[@]}" "Exit"; do
case "$file" in
"Exit")
    exit 0
    ;;
"")
    echo "Invalid selection."
    ;;
*)
    target_files=("$file")
    break
    ;;
esac
done
fi

# 3. EXECUTION LOOP
for script in "${target_files[@]}"; do
echo -e "\n--- Step 1: Running BN Estimation ($script) ---"

output_csv=$(python3 "$script" | grep "Results saved to:" | cut -d ":" -f 2 | xargs)

if [ -f "$output_csv" ]; then
    echo "--- Step 2: Fetching Postgres Estimates from '$selected_db' ---"

    final_csv="${output_csv%.csv}_final.csv"
    echo "query_sql,true_cardinality,bn_est_cardinality,pg_est_cardinality" > "$final_csv"

    # Determine column count dynamically
    header=$(head -n 1 "$output_csv" | tr -d '\r')
    num_cols=$(echo "$header" | awk -F, '{print NF}')

    tail -n +2 "$output_csv" | while IFS=, read -r c1 c2 c3 c4 c5
    do
        # Assign variables based on the number of columns in the CSV
        if [ "$num_cols" -eq 5 ]; then
            # Binned mode (5 columns)
            sa_query="$c1"
            pg_query="$c2"
            true_card="$c3"
            bn_est="$c4"
        else
            # Standard mode (4 columns)
            sa_query="$c1"
            pg_query="$c1"
            true_card="$c2"
            bn_est="$c3"
        fi

        # Remove quotes cleanly
        clean_sa_query=$(echo "$sa_query" | tr -d '"')
        clean_pg_query=$(echo "$pg_query" | tr -d '"')

        # Execute PG query, surfacing PostgreSQL's exact error if it fails
        pg_err=$(mktemp)
        if ! pg_raw_json=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$selected_db" -t -c "EXPLAIN (FORMAT JSON) $clean_pg_query" 2>"$pg_err"); then
            echo "ERROR: PostgreSQL rejected the query:"
            echo "  Query: $clean_pg_query"
            sed 's/^/  /' "$pg_err"
            rm -f "$pg_err"
            exit 1
        fi
        rm -f "$pg_err"

        # Bulletproof PG row extraction
        pg_rows=$(echo "$pg_raw_json" | grep -Eo '"Plan Rows": [0-9]+' | grep -Eo '[0-9]+' | head -1)

        if [ -z "$pg_rows" ]; then
            pg_rows="0"
            echo "Warning: Could not get PG estimate."
        fi

        echo "\"$clean_pg_query\",$true_card,$bn_est,$pg_rows" >> "$final_csv"

        echo "--- Query Processed ---"
        echo "  [Source]  : $clean_sa_query"
        echo "  [SQL/Join]: $clean_pg_query"
        echo "  -> BN: $bn_est | PG: $pg_rows | True: $true_card"
    done || exit 1

    echo -e "\nSUCCESS: Comparison saved to: $final_csv"
    # Machine-readable result path for orchestration scripts
    echo "BENCH_FINAL_CSV=$final_csv"
else
    echo "Error: Python script failed to generate a result file."
    exit 1
fi

done
