# AnnealBN-CE Reproduction Package

Code and reproduction package for the master thesis
*Cardinality Estimation with Annealing-Learned Bayesian Networks*
(University of Passau). The pipeline learns Bayesian-network structures with
simulated annealing (SA) and simulated quantum annealing (SQA), estimates
query cardinalities from them, and compares against a Chow–Liu baseline and
the PostgreSQL planner.

This README describes the experiments, the order they run in, the single
command that reproduces them, and where to find the results. For a
detailed description of every script, dataset format, and output file, see
[docs/USAGE.md](docs/USAGE.md). The thesis itself is at
[docs/Master Thesis.pdf](docs/Master%20Thesis.pdf).

## The reproduction workflow at a glance

1. **Clone and build without errors.** One command builds self-contained
   Docker images: the code is copied into the image at build time, and only
   the results directory is mounted back out.
2. **One script runs everything.** It bootstraps the containers, executes
   experiments E0–E8 inside them in order, and exposes every artefact on
   the host in `./results/`.
3. **Results regenerate from the original data.** All datasets are
   committed or generated deterministically (WetGrass: expected-value
   generation; Market Basket: fixed seed; NHANES and TPC-DS: committed CSVs). No
   external downloads are required.
4. **Inspect the results.** The run ends by generating
   `results/index.html`, which displays the current run’s estimates,
   q-error summaries and comparison charts for all datasets.

Dataset preparation also loads a 10,000-row, eight-column TPC-DS `store_sales`
sample into PostgreSQL and generates its encoded solver input. See the
[dataset instructions](docs/USAGE.md#18-tpc-ds-store-sales-sample) and
[20-query workload](workloads/tpcds_store_sales.csv).
It runs automatically through the one-button workflow. To run it separately, use
`docker compose exec -T app bash scripts/run_tpcds_store_sales.sh`:
SA uses 20 trials × 100 reads; SQA uses 10 trials × 1,000 reads.
Results go to `results/tpcds_store_sales/`.

The [workloads](workloads/) contain 20 queries per dataset, with PostgreSQL
counts in [reference_results/](reference_results/). Both estimator pipelines
read these files.
See [workload details](docs/USAGE.md#19-shared-query-workloads).

## Requirements

- **Docker Desktop, installed and running** — the only prerequisite on
  every platform; everything else runs inside the container (tested with
  Docker 27–29, Compose v2+)
- A few GB of free disk space

## Quick start: reproduce everything

```bash
git clone --branch btw2027 https://github.com/Matea166/MasterUniPassau.git
cd MasterUniPassau
```

Then run the entry point for your platform:

| Platform | Full reproduction | Fast smoke test (headline configs only) |
|----------|-------------------|------------------------------------------|
| macOS / Linux | `./reproduce_all.sh` | `QUICK=1 ./reproduce_all.sh` |
| Windows (CMD or PowerShell) | `.\reproduce_all.bat` | PowerShell: `$env:QUICK=1; .\reproduce_all.bat` |

Both entry points are thin wrappers around the same in-container sequence
(`scripts/run_all.sh`), so every platform runs the identical pipeline:
build the images, start PostgreSQL, prepare all datasets, run the historical
experiments E1–E6 and the fixed TPC-DS experiment E7, and write every
table and figure to `./results/`, ending with the report
`results/index.html`.

> **Runtime.** The full reproduction executes the historical read/trial
> sweeps, the baselines, the 1000-matrix random-structure check and TPC-DS.
> Plan for several hours, keep
> the machine plugged in, and prevent it from sleeping (macOS:
> `caffeinate -i ./reproduce_all.sh`; Windows: set sleep to "Never" while
> plugged in). `QUICK=1` reduces the historical experiments to their headline
> configurations. TPC-DS keeps SA at 20 trials × 100 reads and SQA at
> 10 trials × 1,000 reads in both modes. The total runtime of the expanded
> workflow has not yet been measured.

## Mapping between experiments and thesis results

`reproduce_all` runs the experiments top to bottom in this order:

| ID | Experiment | Script | Output in `results/` | Thesis reference |
|----|------------|--------|----------------------|------------------|
| E0 | Dataset preparation | `scripts/prepare_datasets.sh` | (databases + files inside the container) | Section 6.3, Table 6.1 |
| E1 | WetGrass, N = 100 | `scripts/run_wetgrass_100.sh` | `wetgrass_100/` | Tables 6.3–6.4 |
| E2 | WetGrass, N = 10,000 | `scripts/run_wetgrass_10000.sh` | `wetgrass_10000/` | Tables 6.5–6.6 |
| E3 | NHANES, N = 2,278 | `scripts/run_nhanes.sh` | `nhanes/` | Tables 6.7–6.9 |
| E4 | Market Basket, N = 100 | `scripts/run_market_basket_100.sh` | `market_basket_100/` | Tables 6.10–6.13, Figure 6.1 |
| E5 | Market Basket, N = 10,000 | `scripts/run_market_basket_10000.sh` | `market_basket_10000/` | Tables 6.15–6.18 |
| E6 | Random-structure robustness check | `scripts/run_random_control.sh` | `random_control/` | Table 6.14 |
| E7 | TPC-DS Store Sales, N = 10,000 | `scripts/run_tpcds_store_sales.sh` | `tpcds_store_sales/` | New experiment |
| E8 | Summary tables + report | `scripts/make_report.sh` | `*/reproduced_tables/`, `index.html` | Chapter 6 tables and TPC-DS |

Each experiment folder contains, under stable names:

- `estimates/estimates_<SOLVER>_T<trials>_R<reads>.csv` — per-structure cardinality estimates for every grid configuration
- `qerrors/qerrors_<SOLVER>_T<trials>_R<reads>.csv` — per-structure, per-query q-errors
- `chowliu_pg_final.csv` — true cardinalities, Chow–Liu, and PostgreSQL estimates
- `combined_results.{csv,png}` — merged headline comparison (grouped bar chart)
- `reproduced_tables/table_*.csv` — summary tables from the current run (written by E8)
- `logs/` — full logs of every step
- `configurations.csv` — solver budgets used in the current run

TPC-DS uses `reproduced_tables/cardinality_estimates.csv`,
`qerror_summary.csv` and `solver_settings.csv`. These retain the query IDs,
full-precision estimates, clamped q-errors and separate SA/SQA budgets.
The HTML rounds displayed numbers only.

All datasets use the same experiment runner and report-table calculation.
Estimator CSVs retain full precision. Reports use the current run's
configuration list, so an earlier full run cannot add old sweep results to
a later quick run. An interrupted experiment blocks report generation
until that experiment is rerun successfully.

## Reading the results

Open `results/index.html` after a run to view the generated tables and
charts. CSV downloads retain the recorded values; the HTML rounds numbers
for display. Detailed per-structure estimates are available under
`results/<experiment>/estimates/`.

Evaluations use **clamped q-error**: both counts are floored at 1 for
scoring only. Exact-match percentages compare the original counts, with
absolute tolerance `1e-9`. The full convention is documented in
[USAGE Section 4.2](docs/USAGE.md#42-q-error-calculation).

SA and SQA are stochastic, so structures and estimates can vary between
runs. The report shows the results obtained in the current run.

## Running a single experiment

```bash
docker compose up -d --build
docker compose exec app bash scripts/prepare_datasets.sh   # E0, once
docker compose exec app bash scripts/run_wetgrass_100.sh   # any experiment
docker compose exec app bash scripts/make_report.sh        # E8, refresh report
```

Each experiment reads its frozen configuration from `config/<name>.env`
(dataset names, database/table, and the Table 6.2 trials/reads grid) and
writes only to its own `results/<name>/` folder — experiments never
overwrite each other. Run E0 first; E6's report row additionally references
E4's outputs. `docker compose exec -e QUICK=1 app bash scripts/run_<name>.sh`
runs just the headline configuration of a historical experiment. TPC-DS
always uses the two fixed settings in its configuration file.

The interactive menus (`bnsl-qa/dispatch.sh`, `bnsl/cardinality_benchmarks.sh`,
…) remain available for exploratory use inside the container; they are not
part of the reproduction path. See [docs/USAGE.md](docs/USAGE.md).

To check the supported single-table SA/SQA workflow without running the
experiments:

```bash
docker compose run --build --rm --no-deps app python -m unittest discover -s tests -v
```

The copied upstream tests under `bnsl/tldks_2020/tests/` target the older
`phd` package and are separate from this maintained suite. Join estimation
and hardware backends are outside the validated experiment workflow.

## Licence

This repository is a mixed-licence academic reproducibility repository. It
contains original project code together with material adapted from
third-party open-source repositories (`BNSL-QA-PYTHON`, GPL-2.0;
`tldks-2020`, Apache-2.0). Full licence and attribution information:
[LICENSE.md](LICENSE.md), [NOTICE.md](NOTICE.md),
[THIRD_PARTY_LICENSES/](THIRD_PARTY_LICENSES/).
