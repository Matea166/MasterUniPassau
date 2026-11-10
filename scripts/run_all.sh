#!/usr/bin/env bash
source "$(dirname "$0")/lib.sh"

run_step() {
    echo ""
    echo "=== $1 ==="
    bash "$REPO_ROOT/$2"
}

run_step "E0: dataset preparation"                   scripts/prepare_datasets.sh
run_step "E1: WetGrass N=100"                        scripts/run_wetgrass_100.sh
run_step "E2: WetGrass N=10,000"                     scripts/run_wetgrass_10000.sh
run_step "E3: NHANES"                                scripts/run_nhanes.sh
run_step "E4: Market Basket N=100"                   scripts/run_market_basket_100.sh
run_step "E5: Market Basket N=10,000"                scripts/run_market_basket_10000.sh
run_step "E6: random-structure robustness check"     scripts/run_random_control.sh
run_step "E7: TPC-DS Store Sales N=10,000"            scripts/run_tpcds_store_sales.sh
run_step "E8: summary tables and comparison report"  scripts/make_report.sh

echo ""
echo "All experiments complete. Outputs are in results/ (./results/ on the host)."
echo "Open results/index.html for the experiment report."
