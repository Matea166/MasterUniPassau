#!/usr/bin/env bash
# E0: prepare every dataset representation used by the thesis experiments
# (solver TXT files, CSV relations, PostgreSQL databases and tables).
# Generation is deterministic: WetGrass uses expected-value generation,
# Market Basket uses a fixed seed, NHANES is a committed CSV.
#
# Table *content* for WetGrass and Market Basket is imported by the
# individual run_*.sh scripts, because the two dataset sizes share one table.

source "$(dirname "$0")/lib.sh"

log "=== E0: dataset preparation ==="

# --- WetGrass: N=100 and N=10,000, expected-value (variance-zero) mode ---
log "WetGrass: generating solver TXT files"
(cd "$REPO_ROOT/bnsl-qa" &&
    python3 -m bnslqa generate problems/WetGrass.json --size 100 --expected --name WetGrass &&
    python3 -m bnslqa generate problems/WetGrass.json --size 10000 --expected --name WetGrass_10000)

log "WetGrass: converting TXT to CSV relations"
(cd "$REPO_ROOT/bnsl/datasets" &&
    INPUT_TXT_FILE=../../bnsl-qa/qa-datasets/WetGrass.txt \
    OUTPUT_CSV_FILE=data/WetGrass_variance_zero.csv python3 txt_to_csv.py &&
    INPUT_TXT_FILE=../../bnsl-qa/qa-datasets/WetGrass_10000.txt \
    OUTPUT_CSV_FILE=data/WetGrass_10000.csv python3 txt_to_csv.py)

log "WetGrass: creating database and table"
ensure_database wetgrass
psql_db wetgrass -c "CREATE TABLE IF NOT EXISTS wetgrass_data (
    cloud CHAR(1), sprinkler VARCHAR(3), rain CHAR(1), wetgrass CHAR(1));"

# --- Market Basket: N=100 and N=10,000, seeded synthetic generation ---
log "Market Basket: generating CSV relations"
(cd "$REPO_ROOT/bnsl/datasets" &&
    NUM_ROWS=100 CSV_FILENAME=data/DataMining_MarketBasket_100.csv \
    python3 gen_synthetic_csv_market_basket.py &&
    NUM_ROWS=10000 CSV_FILENAME=data/DataMining_MarketBasket_10000.csv \
    python3 gen_synthetic_csv_market_basket.py)

log "Market Basket: converting CSV to solver TXT files"
(cd "$REPO_ROOT/bnsl-qa" &&
    CSV_FILENAME=../bnsl/datasets/data/DataMining_MarketBasket_100.csv \
    OUTPUT_FILE=qa-datasets/MarketBasket100.txt python3 Market_Basket_synthetic_data_gen.py &&
    CSV_FILENAME=../bnsl/datasets/data/DataMining_MarketBasket_10000.csv \
    OUTPUT_FILE=qa-datasets/MarketBasket10000.txt python3 Market_Basket_synthetic_data_gen.py)

log "Market Basket: creating database and table"
ensure_database market_basket
psql_db market_basket -c "CREATE TABLE IF NOT EXISTS transactions (
    beer INTEGER, bread INTEGER, cola INTEGER,
    diapers INTEGER, eggs INTEGER, milk INTEGER);"

# --- NHANES: committed CSV, fixed size (N=2,278) ---
log "NHANES: generating solver TXT file"
(cd "$REPO_ROOT/bnsl-qa" && python3 Nhanes_csv_to_txt.py)

# Import unconditionally so reused PostgreSQL volumes (where the image's
# init script does not run again) still end up with the right content.
log "NHANES: creating database and importing CSV"
ensure_database nhanes
psql_db nhanes -c "CREATE TABLE IF NOT EXISTS nhanes_data (
    seqn DOUBLE PRECISION, age_group TEXT, ridageyr DOUBLE PRECISION,
    riagendr DOUBLE PRECISION, paq605 DOUBLE PRECISION,
    bmxbmi DOUBLE PRECISION, lbxglu DOUBLE PRECISION,
    diq010 DOUBLE PRECISION, lbxglt DOUBLE PRECISION,
    lbxin DOUBLE PRECISION);"
(cd "$REPO_ROOT/bnsl/datasets" && python3 csv_to_db_NHANES.py)
psql_db nhanes -c "ANALYZE nhanes_data;"

log "TPC-DS: checking the fixed sample and importing CSV"
python3 "$REPO_ROOT/bnsl/datasets/gen_tpcds_sample.py" --check
python3 -m bnsl.datasets.tpcds_encoding
ensure_database tpcds
psql_db tpcds --single-transaction \
    -c "CREATE TABLE IF NOT EXISTS store_sales (
        ss_quantity INTEGER, ss_sales_price NUMERIC(7,2),
        ss_coupon_amt NUMERIC(7,2), ss_net_profit NUMERIC(7,2),
        ss_wholesale_cost NUMERIC(7,2), ss_net_paid NUMERIC(7,2),
        ss_list_price NUMERIC(7,2), ss_store_sk INTEGER);
        TRUNCATE TABLE store_sales;" \
    -c "\copy store_sales (ss_quantity, ss_sales_price, ss_coupon_amt, ss_net_profit, ss_wholesale_cost, ss_net_paid, ss_list_price, ss_store_sk) FROM '$REPO_ROOT/bnsl/datasets/data/TPCDS_store_sales_10000.csv' WITH (FORMAT csv, HEADER true, NULL '')" \
    -c "ANALYZE store_sales;" \
    -c "SELECT count(*) AS tpcds_rows FROM store_sales;"

log "=== E0 complete: all datasets prepared ==="
