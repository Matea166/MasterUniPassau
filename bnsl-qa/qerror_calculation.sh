#!/usr/bin/env bash
set -euo pipefail

# The selected dataset is used for result naming.
# The cardinality script itself must be consistent with the selected dataset.

BASE_DIR="./dispatch_output/solver_outputs"
OUTPUT_BASE="q-error_output"
TMP_DIR="tmp_cardinality_runs"
DATASETS_DIR="../bnsl/datasets/data"

# Docker Compose internal PostgreSQL connection.
# This script is meant to be run from inside the app container.
DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_PASSWORD="${POSTGRES_PASSWORD:-postgres}"

export PGPASSWORD="$DB_PASSWORD"

mkdir -p "$OUTPUT_BASE"
mkdir -p "$TMP_DIR"

timestamp=$(date +"%Y-%m-%d_%H-%M-%S")

echo "==============================="
echo " Select Cardinality Script"
echo "==============================="

mapfile -t scripts < <(ls cardinality_estimation/cardinality_estimation_*.py 2>/dev/null)

if [ ${#scripts[@]} -eq 0 ]; then
    echo "No cardinality_estimation_*.py files found."
    exit 1
fi

select script in "${scripts[@]}"; do
    if [[ -n "$script" ]]; then
        CARD_SCRIPT="$script"
        break
    else
        echo "Invalid selection."
    fi
done

echo "Selected: $CARD_SCRIPT"

echo
echo "==============================="
echo " Select CSV dataset"
echo "==============================="

mapfile -t datasets < <(ls "$DATASETS_DIR"/*.csv 2>/dev/null)

if [ ${#datasets[@]} -eq 0 ]; then
    echo "No CSV datasets found in $DATASETS_DIR"
    exit 1
fi

select dataset in "${datasets[@]}"; do
    if [[ -n "$dataset" ]]; then
        DATASET="$dataset"
        DATASET_NAME=$(basename "$dataset" .csv)
        break
    else
        echo "Invalid selection."
    fi
done

echo "Selected dataset: $DATASET"

echo
echo "==============================="
echo " Select adjacency matrix folder (SA or SQA)"
echo "==============================="

mapfile -t matrix_dirs < <(ls -d "$BASE_DIR"/*/* 2>/dev/null)

if [ ${#matrix_dirs[@]} -eq 0 ]; then
    echo "No adjacency matrix folders found in $BASE_DIR"
    exit 1
fi

select matrix_folder in "${matrix_dirs[@]}"; do
    if [[ -n "$matrix_folder" ]]; then
        MATRIX_DIR="$matrix_folder"
        METHOD=$(basename "$(dirname "$matrix_folder")")
        break
    else
        echo "Invalid selection."
    fi
done

echo "Selected folder: $MATRIX_DIR ($METHOD)"

echo
echo "==============================="
echo " Select database in PostgreSQL"
echo "==============================="
echo "Connection: $DB_HOST:$DB_PORT"

mapfile -t db_list < <(
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -t -A \
    -c "SELECT datname FROM pg_database WHERE datistemplate = false AND datname <> 'postgres' ORDER BY datname;"
)

if [ ${#db_list[@]} -eq 0 ]; then
    echo "Error: Could not find any non-default databases in PostgreSQL at $DB_HOST:$DB_PORT."
    exit 1
fi

select selected_db in "${db_list[@]}"; do
    if [[ -n "$selected_db" ]]; then
        echo "Using database: $selected_db"
        break
    else
        echo "Invalid selection."
    fi
done

# Extract executions and reads from folder name.
BASENAME=$(basename "$MATRIX_DIR")
IFS='_' read -r _ _ _ _ _ EXECUTIONS READS REST <<< "$BASENAME"

RESULT_FILE="$OUTPUT_BASE/results_${DATASET_NAME}_${METHOD}_${EXECUTIONS}_${READS}_${timestamp}.csv"
echo "method,graph_index,query_sql,estimated_cardinality,true_cardinality,q_error" > "$RESULT_FILE"


process_folder () {
    METHOD=$1
    FILE_PATH=$2

    echo "Processing $METHOD"

    matrix_index=0

    if [ ! -f "$FILE_PATH" ]; then
        echo "Error: adjacency matrix file not found: $FILE_PATH"
        exit 1
    fi

    awk '
    /Solution adjacency matrix:/ {
        matrix=""
        while (getline line) {
            if (line ~ /^\[/) {
                gsub(/\[/,"",line)
                gsub(/\]/,"",line)
                if (matrix == "") {
                    matrix="[" line "]"
                } else {
                    matrix=matrix ",[" line "]"
                }
            } else {
                break
            }
        }
        print "[" matrix "]"
    }' "$FILE_PATH" |

    while read -r matrix; do
        matrix_index=$((matrix_index+1))
        OUT_DIR="$TMP_DIR/${METHOD}_graph_$matrix_index"
        mkdir -p "$OUT_DIR"

        python3 "$CARD_SCRIPT" "$matrix" "$OUT_DIR" "$matrix_index"

        CSV="$OUT_DIR/graph_${matrix_index}_cardinality.csv"

        if [[ -f "$CSV" ]]; then

            mapfile -t queries_sql < <(python3 - <<EOF
import ast

with open("$CARD_SCRIPT") as f:
    tree = ast.parse(f.read())

for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if getattr(target, "id", None) == "queries_sql":
                for elt in node.value.elts:
                    print(elt.value)
EOF
)

            i=0

            tail -n +2 "$CSV" | while IFS=, read -r _ est; do
                sql="${queries_sql[$i]}"
                i=$((i+1))

                true_card=$(
                    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$selected_db" \
                    -t -A -c "EXPLAIN ANALYZE $sql" |
                    grep "actual time" |
                    head -1 |
                    sed -E 's/.*rows=([0-9]+).*/\1/'
                )

                if [[ -z "$true_card" ]]; then
                    true_card=0
                    echo "Warning: Could not get true cardinality for query: $sql"
                fi

                qerr=$(python3 - <<PYEOF
est=float("$est")
act=float("$true_card")
if est == 0 or act == 0:
    print(max(est, act))
else:
    print(max(est / act, act / est))
PYEOF
)

                echo "$METHOD,$matrix_index,\"$sql\",$est,$true_card,$qerr" >> "$RESULT_FILE"
            done

            python3 - <<EOF
import pandas as pd

df = pd.read_csv("$RESULT_FILE")
df["avg_q_error"] = df.groupby("query_sql")["q_error"].transform("mean")
df["median_q_error"] = df.groupby("query_sql")["q_error"].transform("median")
df.to_csv("$RESULT_FILE", index=False)
EOF

        fi
    done
}

process_folder "$METHOD" "$MATRIX_DIR/adjacency_matrix.txt"

echo
echo "================================"
echo "Finished"
echo "Results saved in:"
echo "$RESULT_FILE"
echo "================================"
