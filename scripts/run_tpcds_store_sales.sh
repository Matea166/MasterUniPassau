#!/usr/bin/env bash
source "$(dirname "$0")/lib.sh"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
run_ce_experiment config/tpcds_store_sales.env
