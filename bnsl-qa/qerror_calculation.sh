#!/usr/bin/env bash

# The selected dataset is used for result naming.
# The cardinality script itself must be consistent with the selected dataset.

BASE_DIR="./dispatch_output/solver_outputs"
OUTPUT_BASE="q-error_output"
TMP_DIR="tmp_cardinality_runs"
DATASETS_DIR="../bnsl/datasets/data"

DB_CONTAINER="job_db_fixed"
DB_USER="postgres"


mkdir -p "$OUTPUT_BASE"
mkdir -p "$TMP_DIR"

timestamp=$(date +"%Y-%m-%d_%H-%M-%S")

echo "==============================="
echo " Select Cardinality Script"
echo "==============================="

mapfile -t scripts < <(ls cardinality_estimation/cardinality_estimation_*.py)

select script in "${scripts[@]}"; do
    if [[ -n "$script" ]]; then
        CARD_SCRIPT="$script"
        break
    fi
done

echo "Selected: $CARD_SCRIPT"

echo
echo "==============================="
echo " Select CSV dataset"
echo "==============================="

mapfile -t datasets < <(ls "$DATASETS_DIR"/*.csv)

select dataset in "${datasets[@]}"; do
    if [[ -n "$dataset" ]]; then
        DATASET="$dataset"
        DATASET_NAME=$(basename "$dataset" .csv)
        break
    fi
done

echo "Selected dataset: $DATASET"

echo
echo "==============================="
echo " Select adjacency matrix folder (SA or SQA)"
echo "==============================="

mapfile -t matrix_dirs < <(ls -d $BASE_DIR/*/*)

select matrix_folder in "${matrix_dirs[@]}"; do
    if [[ -n "$matrix_folder" ]]; then
        MATRIX_DIR="$matrix_folder"
        METHOD=$(basename $(dirname "$matrix_folder"))
        break
    fi
done

echo "Selected folder: $MATRIX_DIR ($METHOD)"

echo
echo "==============================="
echo " Select database in Docker ($DB_CONTAINER)"
echo "==============================="

db_list=($(docker exec $DB_CONTAINER psql -U $DB_USER -t -c "SELECT datname FROM pg_database WHERE datistemplate = false;"))

select selected_db in "${db_list[@]}"; do
    if [[ -n "$selected_db" ]]; then
        echo "Using database: $selected_db"
        break
    fi
done

# ---- UPDATED: Extract executions and reads from folder name ----
BASENAME=$(basename "$MATRIX_DIR")
IFS='_' read -r _ _ _ _ _ EXECUTIONS READS REST <<< "$BASENAME"

RESULT_FILE="$OUTPUT_BASE/results_${DATASET_NAME}_${METHOD}_${EXECUTIONS}_${READS}_${timestamp}.csv"
echo "method,graph_index,query_sql,estimated_cardinality,true_cardinality,q_error" > "$RESULT_FILE"


process_folder () {

    METHOD=$1
    FILE_PATH=$2

    echo "Processing $METHOD"

    matrix_index=0

    # ---- FIXED MATRIX PARSER (supports any size) ----
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

    while read matrix; do

        matrix_index=$((matrix_index+1))
        OUT_DIR="$TMP_DIR/${METHOD}_graph_$matrix_index"
        mkdir -p "$OUT_DIR"

        python "$CARD_SCRIPT" "$matrix" "$OUT_DIR" "$matrix_index"

        CSV="$OUT_DIR/graph_${matrix_index}_cardinality.csv"

        if [[ -f "$CSV" ]]; then

            # ---- Extract queries_sql safely from Python file ----
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

                true_card=$(docker exec $DB_CONTAINER psql -U $DB_USER -d "$selected_db" \
                -t -A -c "EXPLAIN ANALYZE $sql" | \
                grep "actual time" | head -1 | sed -E 's/.*rows=([0-9]+).*/\1/')

                if [[ -z "$true_card" ]]; then
                    true_card=0
                    echo "Warning: Could not get true cardinality for query: $sql"
                fi

                qerr=$(python3 - <<PYEOF
est=float("$est")
act=float("$true_card")
if est==0 or act==0:
    print(max(est,act))
else:
    print(max(est/act,act/est))
PYEOF
)

                echo "$METHOD,$matrix_index,\"$sql\",$est,$true_card,$qerr" >> "$RESULT_FILE"

            done

            python3 - <<EOF
import pandas as pd
df = pd.read_csv("$RESULT_FILE")
df['avg_q_error'] = df.groupby('query_sql')['q_error'].transform('mean')
df['median_q_error'] = df.groupby('query_sql')['q_error'].transform('median')
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
