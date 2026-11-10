#!/usr/bin/env bash
source "$(dirname "$0")/lib.sh"
source "$REPO_ROOT/config/tpcds_store_sales.env"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1

exp_dir="$RESULTS_ROOT/$EXPERIMENT"
log_dir="$exp_dir/logs"
mkdir -p "$exp_dir/estimates" "$exp_dir/qerrors" "$log_dir"
csv_path="$REPO_ROOT/bnsl/datasets/data/$CSV_NAME.csv"

python3 "$REPO_ROOT/bnsl/datasets/gen_tpcds_sample.py" --check
python3 -m bnsl.datasets.tpcds_encoding
ensure_database "$DB_NAME"
psql_db "$DB_NAME" --single-transaction \
    -c "CREATE TABLE IF NOT EXISTS $TABLE_NAME (
        ss_quantity INTEGER, ss_sales_price NUMERIC(7,2),
        ss_coupon_amt NUMERIC(7,2), ss_net_profit NUMERIC(7,2),
        ss_wholesale_cost NUMERIC(7,2), ss_net_paid NUMERIC(7,2),
        ss_list_price NUMERIC(7,2), ss_store_sk INTEGER);
        TRUNCATE TABLE $TABLE_NAME;" \
    -c "\copy $TABLE_NAME FROM '$csv_path' WITH (FORMAT csv, HEADER true, NULL '')" \
    -c "ANALYZE $TABLE_NAME;"

for solver in SA SQA; do
    trials_var="${solver}_TRIALS"
    reads_var="${solver}_READS"
    trials="${!trials_var}"
    reads="${!reads_var}"
    tag="${solver}_T${trials}_R${reads}"
    dlog="$log_dir/dispatch_$tag.log"
    log "[$EXPERIMENT] $tag: solver + cardinality estimation"
    (cd "$REPO_ROOT/bnsl-qa" &&
        DATASET_TXT="$SOLVER_TXT" SOLVER="$solver" TRIALS="$trials" READS="$reads" \
        CE_SCRIPT="$CE_SCRIPT_QA" CE_DATASET_CSV="$csv_path" \
        bash dispatch.sh) 2>&1 | tee "$dlog"

    solver_dir=$(extract_result_var DISPATCH_SOLVER_DIR "$dlog")
    final_csv=$(extract_result_var DISPATCH_FINAL_CSV "$dlog")
    if [ -z "$final_csv" ] || [ ! -f "$REPO_ROOT/bnsl-qa/$final_csv" ]; then
        echo "Error: no estimates produced for $tag." >&2
        exit 1
    fi
    cp "$REPO_ROOT/bnsl-qa/$final_csv" "$exp_dir/estimates/estimates_$tag.csv"

    qlog="$log_dir/qerror_$tag.log"
    (cd "$REPO_ROOT/bnsl-qa" &&
        CARD_SCRIPT="$CE_SCRIPT_QA" DATASET_CSV="$csv_path" \
        MATRIX_DIR="$solver_dir" QERROR_DB="$DB_NAME" CE_DATASET_CSV="$csv_path" \
        bash qerror_calculation.sh) 2>&1 | tee "$qlog"
    qerr_file=$(extract_result_var QERROR_RESULT_FILE "$qlog")
    if [ -z "$qerr_file" ] || [ ! -f "$REPO_ROOT/bnsl-qa/$qerr_file" ]; then
        echo "Error: no q-errors produced for $tag." >&2
        exit 1
    fi
    cp "$REPO_ROOT/bnsl-qa/$qerr_file" "$exp_dir/qerrors/qerrors_$tag.csv"
done

blog="$log_dir/chowliu.log"
(cd "$REPO_ROOT/bnsl" &&
    BENCH_DB="$DB_NAME" BENCH_SCRIPT="$CE_SCRIPT_CL" CE_DATASET_CSV="$csv_path" \
    bash cardinality_benchmarks.sh) 2>&1 | tee "$blog"
bench_final=$(extract_result_var BENCH_FINAL_CSV "$blog")
if [ -z "$bench_final" ] || [ ! -f "$bench_final" ]; then
    echo "Error: no tree/PostgreSQL comparison produced." >&2
    exit 1
fi
cp "$bench_final" "$exp_dir/chowliu_pg_final.csv"

(cd "$REPO_ROOT/bnsl" &&
    SA_FILE="$exp_dir/estimates/estimates_SA_T${SA_TRIALS}_R${SA_READS}.csv" \
    SQA_FILE="$exp_dir/estimates/estimates_SQA_T${SQA_TRIALS}_R${SQA_READS}.csv" \
    BN_FILE="$exp_dir/chowliu_pg_final.csv" MERGE_OUTPUT_DIR="$exp_dir" \
    bash merge_results.sh) 2>&1 | tee "$log_dir/merge.log"

newest_csv=$(ls -t "$exp_dir"/combined_results_*.csv | head -1)
newest_png=$(ls -t "$exp_dir"/combined_results_*.png | head -1)
cp "$newest_csv" "$exp_dir/combined_results.csv"
cp "$newest_png" "$exp_dir/combined_results.png"
log "[$EXPERIMENT] complete — outputs in results/$EXPERIMENT/"
