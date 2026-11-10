#!/usr/bin/env bash
# E6: random-structure robustness check — reproduces the "Random structures"
# side of thesis Table 6.14. Generates admissible random DAGs (acyclic,
# max 2 parents) and evaluates them with the same Market Basket N=100
# cardinality-estimation script and workload as the annealing runs.
source "$(dirname "$0")/lib.sh"

# Load the check's own parameters first, then the base dataset settings
# (CSV_NAME, DB_NAME, TABLE_NAME, CE_SCRIPT_QA come from the base config).
source "$REPO_ROOT/config/random_control.env"
source "$REPO_ROOT/$BASE_CONFIG"

exp_dir="$RESULTS_ROOT/random_control"
log_dir="$exp_dir/logs"
mkdir -p "$log_dir"
touch "$exp_dir/.running"

matrices_count="$NUM_MATRICES"
if [ "$QUICK" = "1" ]; then
    matrices_count="$QUICK_NUM_MATRICES"
fi

csv_rel="data/${CSV_NAME}.csv"
csv_from_qa="../bnsl/datasets/data/${CSV_NAME}.csv"

if [ ! -f "$REPO_ROOT/bnsl/datasets/$csv_rel" ]; then
    echo "Error: dataset CSV missing — run scripts/prepare_datasets.sh first."
    exit 1
fi

log "[random_control] importing ${CSV_NAME}.csv into $DB_NAME.$TABLE_NAME"
ensure_database "$DB_NAME"
import_csv_into_db "$DB_NAME" "$TABLE_NAME" "$csv_rel"

log "[random_control] generating $matrices_count random DAG matrices ($NUM_VARS variables)"
(cd "$REPO_ROOT/bnsl-qa" &&
    RNG_ACTION=generate NUM_VARS="$NUM_VARS" NUM_MATRICES="$matrices_count" \
    bash RNG_matrix.sh) 2>&1 | tee "$log_dir/generate.log"

matrix_file="RNG_Matrix/matrices/RNG_matrix_${matrices_count}_${NUM_VARS}.txt"

log "[random_control] evaluating random structures with $CE_SCRIPT_QA"
(cd "$REPO_ROOT/bnsl-qa" &&
    RNG_ACTION=estimate CARD_SCRIPT="$CE_SCRIPT_QA" MATRIX_FILE="$matrix_file" \
    CE_DATASET_CSV="$csv_from_qa" \
    bash RNG_matrix.sh) 2>&1 | tee "$log_dir/estimate.log"

out_dir=$(extract_result_var RNG_OUTPUT_DIR "$log_dir/estimate.log")
if [ -z "$out_dir" ] || [ ! -f "$REPO_ROOT/bnsl-qa/$out_dir/final_queries_cardinality.csv" ]; then
    echo "Error: random-structure run produced no final CSV (see $log_dir/estimate.log)"
    exit 1
fi

cp "$REPO_ROOT/bnsl-qa/$out_dir/final_queries_cardinality.csv" "$exp_dir/final_queries_cardinality.csv"
cp "$REPO_ROOT/bnsl-qa/$matrix_file" "$exp_dir/random_matrices.txt"

rm "$exp_dir/.running"
log "[random_control] complete — outputs in results/random_control/"
