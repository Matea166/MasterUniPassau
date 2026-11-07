#!/usr/bin/env bash
set -euo pipefail

# The selected dataset is used for result naming.
# The cardinality script itself must be consistent with the selected dataset.
#
# Non-interactive mode (used by scripts/run_*.sh): set all of
#   CARD_SCRIPT  cardinality_estimation/cardinality_estimation_<Dataset>.py
#   DATASET_CSV  path to the CSV relation (used for result naming)
#   MATRIX_DIR   dispatch_output/solver_outputs/<SA|SQA>/<run folder>
#   QERROR_DB    PostgreSQL database for true-cardinality queries
# to skip all menus. The last output line is a machine-readable
# QERROR_RESULT_FILE path for orchestration scripts.

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

if [ -n "${CARD_SCRIPT:-}" ] && [ -n "${DATASET_CSV:-}" ] && [ -n "${MATRIX_DIR:-}" ] && [ -n "${QERROR_DB:-}" ]; then
    if [ ! -f "$CARD_SCRIPT" ]; then
        echo "Error: CARD_SCRIPT not found: $CARD_SCRIPT"
        exit 1
    fi
    if [ ! -d "$MATRIX_DIR" ]; then
        echo "Error: MATRIX_DIR not found: $MATRIX_DIR"
        exit 1
    fi
    DATASET="$DATASET_CSV"
    DATASET_NAME=$(basename "$DATASET_CSV" .csv)
    METHOD=$(basename "$(dirname "$MATRIX_DIR")")
    selected_db="$QERROR_DB"
    echo "Script: $CARD_SCRIPT | Dataset: $DATASET_NAME | Matrices: $MATRIX_DIR ($METHOD) | DB: $selected_db"
else

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

fi

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

    python3 -c '
import ast
import re
import sys
import networkx as nx

with open(sys.argv[1]) as f:
    data = f.read()
for match in re.findall(r"Solution adjacency matrix:\n((?:\[.*?\]\n?)+)", data):
    matrix = ast.literal_eval("[" + ",".join(match.strip().splitlines()) + "]")
    graph = nx.DiGraph((i, j) for i, row in enumerate(matrix)
                      for j, value in enumerate(row) if value == 1)
    if nx.is_directed_acyclic_graph(graph):
        print(matrix)
' "$FILE_PATH" |

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

                # Execute the query, surfacing PostgreSQL's exact error if
                # it fails — never record 0 as a real cardinality.
                pg_err=$(mktemp)
                if ! explain_out=$(psql -X -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$selected_db" \
                        -t -A -c "EXPLAIN (ANALYZE, FORMAT JSON, TIMING OFF) $sql" 2>"$pg_err"); then
                    echo "ERROR: PostgreSQL rejected the query:"
                    echo "  Query: $sql"
                    sed 's/^/  /' "$pg_err"
                    rm -f "$pg_err"
                    exit 1
                fi
                rm -f "$pg_err"

                if ! true_card=$(python3 -c '
import json
import math
import sys

actual = json.load(sys.stdin)[0]["Plan"]["Actual Rows"]
if type(actual) not in (int, float) or not math.isfinite(actual) or actual < 0:
    raise ValueError("PostgreSQL actual rows must be finite and non-negative.")
print(actual)
' <<< "$explain_out"); then
                    echo "ERROR: could not read PostgreSQL actual rows for query: $sql" >&2
                    exit 1
                fi

                qerr=$(python3 - <<PYEOF
import math

est=float("$est")
act=float("$true_card")
if not all(math.isfinite(v) and v >= 0 for v in (est, act)):
    raise ValueError("Cardinalities must be finite and non-negative.")
est, act = max(est, 1.0), max(act, 1.0)
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

if [ "$(wc -l < "$RESULT_FILE")" -le 1 ]; then
    rm -f "$RESULT_FILE"
    echo "Error: no valid graphs to evaluate." >&2
    exit 1
fi

echo
echo "================================"
echo "Finished"
echo "Results saved in:"
echo "$RESULT_FILE"
echo "================================"

# Machine-readable result path for orchestration scripts
echo "QERROR_RESULT_FILE=$RESULT_FILE"
