# Usage guide

This guide covers the experiments being prepared for the BTW 2027 Student Program.
See the [README](../README.md) for the project overview and full-run command.
Commands below run from the repository root unless a container directory is given.

## Running experiments

Start Docker Desktop, then choose a full run or a quick workflow check:

| Platform | Full run | Quick check |
|---|---|---|
| macOS / Linux | `QUICK=0 ./reproduce_all.sh` | `QUICK=1 ./reproduce_all.sh` |
| Windows PowerShell | `$env:QUICK=0; .\reproduce_all.bat` | `$env:QUICK=1; .\reproduce_all.bat` |

`FRESH=1` is the default and recreates the project's Docker database volume.
To keep the volume, prefix the Unix command with `FRESH=0`, or set
`$env:FRESH=0` in PowerShell. The experiment tables are reloaded in either case.

The application image contains the code; only `results/` is shared with the host.
Host edits do not affect a running experiment. Rebuild and recreate the app with
`docker compose up -d --build` before running changed code.

The HTML report ends with an expandable appendix containing each dataset's query IDs and conditions.

### Individual experiments

Prepare all datasets once:

```bash
docker compose up -d --build
docker compose exec -T app bash scripts/prepare_datasets.sh
```

Then run the required script:

| Experiment | Script under `scripts/` | Result directory under `results/` |
|---|---|---|
| WetGrass, 100 rows | `run_wetgrass_100.sh` | `wetgrass_100/` |
| WetGrass, 10,000 rows | `run_wetgrass_10000.sh` | `wetgrass_10000/` |
| NHANES | `run_nhanes.sh` | `nhanes/` |
| Market Basket, 100 rows | `run_market_basket_100.sh` | `market_basket_100/` |
| Market Basket, 10,000 rows | `run_market_basket_10000.sh` | `market_basket_10000/` |
| Random structures | `run_random_control.sh` | `random_control/` |
| TPC-DS sample | `run_tpcds_store_sales.sh` | `tpcds_store_sales/` |

For example:

```bash
docker compose exec -T app bash scripts/run_tpcds_store_sales.sh
docker compose exec -T app bash scripts/make_report.sh
```

Set `-e QUICK=1` before `app` to use quick mode. Parameters are in
[`config/`](../config/): reads are samples per solver run, and trials are
independent runs. Quick mode uses the headline configuration for WetGrass,
NHANES and Market Basket. TPC-DS always uses SA 20 × 100 and SQA 10 × 1,000
(trials × reads).

The random check evaluates up to 1,000 generated DAGs on Market Basket, 100 rows;
quick mode requests 20. Graphs have at most two parents per node. Run the Market
Basket experiment first to include its SA/SQA rows in the comparison report.

## Repository layout

| Directory | Purpose |
|---|---|
| `bnsl-qa/` | Annealing solvers, integer TXT converters and BN estimation |
| `bnsl/` | Tree estimator, dataset utilities, PostgreSQL comparison and plotting |
| `scripts/` | Automated experiments and report generation |
| `config/` | Dataset paths, databases and solver budgets |
| `workloads/` | Shared SQL queries with stable IDs |
| `reference_results/` | Saved PostgreSQL measurements, settings and input hashes |
| `tests/` | Maintained checks for scoring, grouping, queries and workflow behavior |
| `docker/` | Container setup and database initialization |

Generated solver inputs go in `bnsl-qa/qa-datasets/`. CSV relations are in
`bnsl/datasets/data/`. The PostgreSQL tables are loaded from those CSVs.

## Datasets

### WetGrass and Market Basket

WetGrass uses expected-value generation from
[`WetGrass.json`](../bnsl-qa/problems/WetGrass.json), then decodes TXT integer
states into readable CSV values. Market Basket uses a fixed-seed CSV generator
and converts its binary values to solver TXT. Both run at 100 and 10,000 rows.

| Task | Script |
|---|---|
| WetGrass TXT → CSV | [`txt_to_csv_wetgrass.py`](../bnsl/datasets/txt_to_csv_wetgrass.py) |
| Market Basket CSV generation | [`gen_synthetic_csv_market_basket.py`](../bnsl/datasets/gen_synthetic_csv_market_basket.py) |
| Market Basket CSV → TXT | [`Market_Basket_synthetic_data_gen.py`](../bnsl-qa/Market_Basket_synthetic_data_gen.py) |

Dataset preparation supplies the filenames and sizes automatically. There is no
need to edit these scripts for the configured experiments.

### NHANES

The included CSV has 2,278 rows. The modeled columns are `age_group`, `BMXBMI`,
`RIAGENDR` and `DIQ010`; none has missing values in this file.

[`grouping_nhanes.py`](../bnsl/datasets/grouping_nhanes.py) defines the shared
BMI groups: [0,18.5), [18.5,25), [25,30), [30,150). The tree keeps original
category labels; annealing uses integer category codes.
[`Nhanes_csv_to_txt.py`](../bnsl-qa/Nhanes_csv_to_txt.py) writes the solver TXT
and category mappings under `bnsl-qa/qa-datasets/`.

The solver column order is `age_group, BMXBMI, RIAGENDR, DIQ010`; the tree's
existing order is `age_group, RIAGENDR, DIQ010, BMXBMI`. Matrix interpretation
must follow the solver order.

### TPC-DS sample

The [CSV](../bnsl/datasets/data/TPCDS_store_sales_10000.csv) contains 10,000
`store_sales` rows, sampled without replacement using seed 2027 from all
2,880,404 rows generated at scale factor 1. It uses
[`tpcds-kit` v2.10.0](https://github.com/gregrahn/tpcds-kit/tree/5a3a81796992b725c2a8b216767e142609966752).
The [metadata](../bnsl/datasets/data/TPCDS_store_sales_10000.json) records the
source commit, seeds, column positions, missing counts and checksums.

| Column | Meaning | PostgreSQL type |
|---|---|---|
| `ss_quantity` | Units purchased | `INTEGER` |
| `ss_sales_price` | Sale price per unit | `NUMERIC(7,2)` |
| `ss_coupon_amt` | Coupon amount for the sale | `NUMERIC(7,2)` |
| `ss_net_profit` | Profit from the sale | `NUMERIC(7,2)` |
| `ss_wholesale_cost` | Wholesale cost per unit | `NUMERIC(7,2)` |
| `ss_net_paid` | Amount paid after coupons | `NUMERIC(7,2)` |
| `ss_list_price` | List price per unit | `NUMERIC(7,2)` |
| `ss_store_sk` | Categorical store identifier | `INTEGER` |

The [source schema](https://github.com/gregrahn/tpcds-kit/blob/5a3a81796992b725c2a8b216767e142609966752/tools/tpcds.sql#L561-L587)
and [pricing code](https://github.com/gregrahn/tpcds-kit/blob/5a3a81796992b725c2a8b216767e142609966752/tools/pricing.c#L140-L199)
define these fields. Net profit is net paid minus quantity × wholesale cost,
so negative values are expected. Raw CSV values are preserved in PostgreSQL;
empty fields become SQL `NULL`.

#### Grouping

Both models use [`grouping_tpcds.py`](../bnsl/datasets/grouping_tpcds.py).
Codes start at zero in the table order below. The final code is a separate
missing state; the tree represents it as `MISSING` and annealing as an integer.
All 10,000 rows are retained, including 856 with at least one missing value.

| Column | Nonmissing groups, in code order | Missing code |
|---|---|---|
| `ss_quantity` | 1–25; 26–50; 51–75; 76–100 | 4 |
| `ss_sales_price` | [0,25); [25,50); [50,100); ≥100 | 4 |
| `ss_coupon_amt` | 0; (0,1000); ≥1000 | 3 |
| `ss_net_profit` | <0; [0,1000); ≥1000 | 3 |
| `ss_wholesale_cost` | [0,25); [25,50); [50,75); ≥75 | 4 |
| `ss_net_paid` | [0,1000); [1000,3000); ≥3000 | 3 |
| `ss_list_price` | [0,50); [50,100); ≥100 | 3 |
| `ss_store_sk` | 1; 2; 4; 7; 8; 10 | 6 |

These groups match the workload predicates and keep conditional tables small.
For example, coupon groups contain 7,674 zero values, 1,322 values between zero
and 1,000, and 562 values at least 1,000; another 442 are missing. Grouping and
TPC-DS solver budgets were selected in exploratory tests on this sample.

Numeric predicates exclude missing states. Unfiltered columns include them
through marginalization, so missingness can affect learning and estimates.
Predicates that cut through a group are rejected. Changing groups requires
regenerating solver input and retraining both models.

[`Tpcds_csv_to_txt.py`](../bnsl-qa/Tpcds_csv_to_txt.py) produces the integer
solver input. To inspect the raw PostgreSQL data after dataset preparation:

```bash
docker compose exec -T postgres psql -U postgres -d tpcds -c "SELECT * FROM store_sales LIMIT 20;"
```

#### Regenerating the sample

A normal run verifies and uses the committed CSV. To regenerate it, enter the app
container with `docker compose exec app bash`, then run:

```bash
git clone https://github.com/gregrahn/tpcds-kit.git /tmp/tpcds-kit
git -C /tmp/tpcds-kit checkout 5a3a81796992b725c2a8b216767e142609966752
cd /tmp/tpcds-kit/tools
make OS=LINUX LINUX_CFLAGS="-g -Wall -fcommon -Wno-error=implicit-int -Wno-error=implicit-function-declaration" dsdgen tpcds.idx
mkdir -p /tmp/tpcds-data
./dsdgen -SCALE 1 -TABLE store_sales -RNGSEED 19620718 -DIR /tmp/tpcds-data
python /workspace/bnsl/datasets/gen_sample_csv_tpcds.py /tmp/tpcds-data/store_sales.dat --output /tmp/TPCDS_store_sales_10000.csv
```

To verify the committed sample independently:

```bash
docker compose exec -T app python bnsl/datasets/gen_sample_csv_tpcds.py --check
```

This is a TPC-DS-derived single-table experiment with custom queries, not an
official TPC-DS benchmark result. See [NOTICE.md](../NOTICE.md) for attribution.

## Workloads

Each file in [`workloads/`](../workloads/) contains `query_id,sql,reason`, with
20 queries covering common and rare combinations, dependencies and full-attribute
selections. Both sizes of each synthetic dataset share a workload. Q01–Q06 retain
the original WetGrass, NHANES and Market Basket queries.

Queries use one table and `AND` predicates. WetGrass and Market Basket support
equality filters; NHANES additionally supports one complete BMI group. TPC-DS
supports comparisons and `IS NULL` / `IS NOT NULL` over complete groups. Joins,
`OR` and partial-group ranges are outside the configured workload.

For exploratory workloads, edit the relevant CSV, retain unique nonempty query
IDs, rebuild the app and rerun the affected experiments. The saved PostgreSQL
references identify their original data and workloads by checksum.

## Estimators and PostgreSQL

SA/SQA learn graph structures with at most two parents. Cyclic structures are
discarded rather than repaired. The resulting networks use pgmpy maximum-likelihood
parameter fitting and variable elimination. Inference failures stop the run.

The tree retains the normalized-MI structure learning and fitting/inference from
the adapted [tldks-2020](https://github.com/MaxHalford/tldks-2020) implementation.
The comparison therefore evaluates the complete estimators.

PostgreSQL 16.15 is pinned by image digest. After loading each table, the workflow
runs `ANALYZE`, then `EXPLAIN (ANALYZE, FORMAT JSON, TIMING OFF)` for each query.
It uses ordinary statistics with the default statistics target of 100, without
extended statistics. Estimates and actual row counts come from the scan plan,
using the same data and predicates as the models.

[`reference_results/`](../reference_results/) contains saved estimates, true counts,
settings and hashes. Each experiment obtains fresh PostgreSQL measurements.

## Metrics

For estimate `E` and true count `C`, clamped q-error is:

```text
E_eval = max(E, 1)
C_eval = max(C, 1)
q_error = max(E_eval / C_eval, C_eval / E_eval)
```

Counts must be finite and nonnegative. Clamping affects scoring only; the recorded
counts remain unchanged. Q-error 1 does not imply an exact prediction when counts
are below one. Exact matches use the original counts with absolute tolerance `1e-9`.

Reports include per-query estimates, median, 95th-percentile and maximum q-error,
plus exact-match percentages. CSVs retain full precision; HTML rounds for display.

For each query, SA/SQA stable estimates use the most frequent two-decimal group.
Ties are resolved by the upper median of the tied group values; the upper-median
original estimate within the chosen group is used for scoring. Read/trial and
random-structure summaries evaluate the per-structure estimates.

## Outputs

Open `results/index.html` after report generation. Each experiment writes to
`results/<experiment>/`:

| Path | Contents |
|---|---|
| `estimates/` | Per-structure SA/SQA estimates, named by solver, trials and reads |
| `qerrors/` | Per-structure query estimates, true counts and q-errors |
| `chowliu_pg_final.csv` | Tree and PostgreSQL estimates with true counts |
| `combined_results.csv` and `.png` | Headline comparison |
| `reproduced_tables/` | Summary tables with query IDs and full-precision estimates |
| `configurations.csv` | Solver configurations executed in the run |
| `logs/` | Execution logs |

The random check writes `final_queries_cardinality.csv`, `random_matrices.txt`
and logs. Report generation also uses the corresponding Market Basket outputs.
Summary filenames for the original datasets retain thesis table numbers; TPC-DS
uses `cardinality_estimates.csv`, `qerror_summary.csv` and `solver_settings.csv`.

Only configurations listed for the current run are summarized. A `.running`
marker blocks reporting after an interrupted experiment; rerun that experiment
successfully before refreshing the report.

## Interactive tools

Enter the app container with `docker compose exec app bash`. The original menus
remain available for exploratory runs:

| Container directory | Command | Purpose |
|---|---|---|
| `/workspace/bnsl-qa` | `bash dispatch.sh` | Learn structures and estimate cardinalities |
| `/workspace/bnsl-qa` | `bash qerror_calculation.sh` | Evaluate stored solver matrices |
| `/workspace/bnsl-qa` | `bash RNG_matrix.sh` | Generate or evaluate random DAGs |
| `/workspace/bnsl` | `bash cardinality_benchmarks.sh` | Run tree and PostgreSQL comparisons |
| `/workspace/bnsl` | `bash merge_results.sh` | Merge estimates and plot comparisons |

Choose the dataset, script and database consistently. Interactive outputs stay
inside the container unless saved under `/workspace/results/`.

## Verification

Run the maintained suite without starting experiments:

```bash
docker compose run --build --rm --no-deps app python -m unittest discover -s tests -v
```

The suite checks mixed-domain scores, grouping, SQL/model row alignment, reporting
and workflow failures. Copied upstream tests in `bnsl/tldks_2020/tests/` target the
older `phd` package and are separate. Joins and hardware backends are outside this
experiment workflow. Full end-to-end validation of the expanded workflow is pending.

## Licence

See [LICENSE.md](../LICENSE.md), [NOTICE.md](../NOTICE.md) and
[THIRD_PARTY_LICENSES/](../THIRD_PARTY_LICENSES/) for licences and source attribution.
