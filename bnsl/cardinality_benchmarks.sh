#!/usr/bin/env bash

# Configuration
DB_CONTAINER="annealbn-ce-postgres"
DB_USER="postgres"
RESULTS_DIR="card_results"

mkdir -p $RESULTS_DIR

echo "==========================================="
echo "   Cardinality Estimation Benchmarker      "
echo "==========================================="

# 1. FETCH DATABASES FROM POSTGRES
echo "--- Fetching available databases from $DB_CONTAINER ---"
db_list=($(docker exec $DB_CONTAINER psql -U $DB_USER -t -c "SELECT datname FROM pg_database WHERE datistemplate = false;"))

if [ ${#db_list[@]} -eq 0 ]; then
    echo "Error: Could not find any databases in $DB_CONTAINER."
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

# 2. FIND PYTHON FILES
files=(cardinality_estimation/cardinality_estimation_*.py)
if [ ${#files[@]} -eq 0 ]; then
    echo "No cardinality_estimation_*.py files found."
    exit 1
fi

echo -e "\nSelect a Python script to run:"
select file in "${files[@]}" "Run All" "Exit"; do
    case $file in
        "Exit") exit 0 ;;
        "Run All") target_files=("${files[@]}") ; break ;;
        *) target_files=("$file") ; break ;;
    esac
done

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

            # Execute PG query
            pg_raw_json=$(docker exec $DB_CONTAINER psql -U $DB_USER -d "$selected_db" -t -c "EXPLAIN (FORMAT JSON) $clean_pg_query")

            # Bulletproof PG row extraction
            pg_rows=$(echo "$pg_raw_json" | grep -Eo '"Plan Rows": [0-9]+' | grep -Eo '[0-9]+' | head -1)

            if [ -z "$pg_rows" ]; then
                pg_rows="0"
                echo "Warning: Could not get PG estimate."
            fi

            # Export
            echo "\"$clean_sa_query\",$true_card,$bn_est,$pg_rows" >> "$final_csv"

            echo "--- Query Processed ---"
            echo "  [SA/Join] : $clean_sa_query"
            echo "  [PG/Exec] : $clean_pg_query"
            echo "  -> BN: $bn_est | PG: $pg_rows | True: $true_card"
        done

        echo -e "\nSUCCESS: Comparison saved to: $final_csv"
    else
        echo "Error: Python script failed to generate a result file."
    fi
done
