# AnnealBN-CE — Reproduction Package

Code and reproduction package for the master thesis
*Cardinality Estimation with Annealing-Learned Bayesian Networks*
(University of Passau). The pipeline learns Bayesian-network structures with
simulated annealing (SA) and simulated quantum annealing (SQA), estimates
query cardinalities from them, and compares against a Chow–Liu baseline and
the PostgreSQL planner.

This README is the reproduction blueprint: which experiments the thesis
reports, the order they run in, the single command that reproduces them,
and how to compare the regenerated outputs against the thesis. For a
detailed description of every script, dataset format, and output file, see
[docs/USAGE.md](docs/USAGE.md). The thesis itself is at
[docs/Master Thesis.pdf](docs/Master%20Thesis.pdf).

## The reproduction workflow at a glance

1. **Clone and build without errors** — one command builds self-contained
   Docker images: the code is copied into the image at build time, and only
   the results directory is mounted back out.
2. **One script runs everything** — it bootstraps the containers, executes
   experiments E0–E7 inside them in order, and exposes every artefact on
   the host in `./results/`.
3. **Results regenerate from the original data** — all datasets are
   committed or generated deterministically (WetGrass: expected-value
   generation; Market Basket: fixed seed; NHANES: committed CSV). No
   external downloads.
4. **Compare with the thesis** — the run ends by generating
   `results/index.html`, which renders every reproduced table next to the
   frozen thesis values from [original_results/](original_results/).

## Requirements

- **Docker Desktop, installed and running** — the only prerequisite on
  every platform; everything else runs inside the container (tested with
  Docker 27–29, Compose v2+)
- A few GB of free disk space

## Quick start — reproduce everything

```bash
git clone https://github.com/Matea166/MasterUniPassau.git
cd MasterUniPassau
```

Then run the entry point for your platform:

| Platform | Full reproduction | Fast smoke test (headline configs only) |
|----------|-------------------|------------------------------------------|
| macOS / Linux | `./reproduce_all.sh` | `QUICK=1 ./reproduce_all.sh` |
| Windows (CMD or PowerShell) | `.\reproduce_all.bat` | PowerShell: `$env:QUICK=1; .\reproduce_all.bat` |

Both entry points are thin wrappers around the same in-container sequence
(`scripts/run_all.sh`), so every platform runs the identical pipeline:
build the images, start PostgreSQL, prepare all datasets, run experiments
E1–E6 with the exact configurations from thesis Table 6.2, and write every
table and figure to `./results/`, ending with the comparison report
`results/index.html`.

> **Runtime disclaimer.** The full reproduction executes the complete
> thesis grid — 84 solver configurations (read and trial sweeps for both SA
> and SQA on every dataset) plus the baselines and the 1000-matrix
> random-structure check — and takes **several hours** (measured:
> 6 h 16 min on an Apple-Silicon MacBook). Plan for an overnight run, keep
> the machine plugged in, and prevent it from sleeping (macOS:
> `caffeinate -i ./reproduce_all.sh`; Windows: set sleep to "Never" while
> plugged in). The `QUICK` smoke test runs one headline configuration per
> experiment in roughly **45 minutes** including the image build and is the
> recommended first run.

## Experiments ↔ thesis mapping

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
| E7 | Summary tables + comparison report | `scripts/make_report.sh` | `*/reproduced_tables/`, `index.html` | Chapter 6 tables |

Each experiment folder contains, under stable names:

- `estimates/estimates_<SOLVER>_T<trials>_R<reads>.csv` — per-structure cardinality estimates for every grid configuration
- `qerrors/qerrors_<SOLVER>_T<trials>_R<reads>.csv` — per-structure, per-query q-errors
- `chowliu_pg_final.csv` — true cardinalities, Chow–Liu, and PostgreSQL estimates
- `combined_results.{csv,png}` — merged headline comparison (grouped bar chart)
- `reproduced_tables/table_*.csv` — reproduced thesis tables (written by E7)
- `logs/` — full logs of every step

## Comparing with the thesis results

The exact values reported in the thesis are frozen under
[original_results/](original_results/) — one CSV per thesis table, plus the
query workloads and Figure 6.1
(see [original_results/MANIFEST.md](original_results/MANIFEST.md) for the
file → table mapping). The run scripts never write there.

SA and SQA are stochastic, so regenerated numbers are **similar but not
necessarily identical** to the originals. `results/index.html` (generated by
E7) renders each reproduced table next to its thesis original so the
comparison is visible at a glance. Judge each table type by the right
standard:

| Table type | Thesis tables | What must match |
|------------|---------------|-----------------|
| Cardinality estimates | 6.3, 6.5, 6.8, 6.10, 6.15 | The stable SA/SQA estimate vectors: exact or near-exact |
| Chow–Liu and PostgreSQL columns | all | Deterministic — must match exactly (same data, same pinned versions) |
| Q-error summaries | 6.4, 6.6, 6.9, 6.11, 6.16 | Min/median/max very close; the ordering between estimators must hold |
| Read/trial variation | 6.12, 6.13, 6.17, 6.18 | Exact structure counts may differ run to run; the trends must hold (more reads → more stable structures, lower q-errors) |
| Random-structure check | 6.14 | Random-side numbers will differ, but annealing structures must show clearly lower median/max q-error than random ones |

A reproduction counts as successful when the stable vectors, the
deterministic columns, and all orderings and trends line up. For stochastic
solvers, bit-identical numbers are not a realistic criterion.

Appendix Tables B.4–B.19 (per-configuration detail listings) are not paired
in the report; their underlying data is regenerated in full and available
under `results/<experiment>/estimates/` — one CSV per configuration — for
manual comparison with the thesis PDF.

## Running a single experiment

```bash
docker compose up -d --build
docker compose exec app bash scripts/prepare_datasets.sh   # E0, once
docker compose exec app bash scripts/run_wetgrass_100.sh   # any experiment
docker compose exec app bash scripts/make_report.sh        # E7, refresh report
```

Each experiment reads its frozen configuration from `config/<name>.env`
(dataset names, database/table, and the Table 6.2 trials/reads grid) and
writes only to its own `results/<name>/` folder — experiments never
overwrite each other. Run E0 first; E6's report row additionally references
E4's outputs. `docker compose exec -e QUICK=1 app bash scripts/run_<name>.sh`
runs just the headline configuration of one experiment.

The interactive menus (`bnsl-qa/dispatch.sh`, `bnsl/cardinality_benchmarks.sh`,
…) remain available for exploratory use inside the container; they are not
part of the reproduction path. See [docs/USAGE.md](docs/USAGE.md).

## Licence

This repository is a mixed-licence academic reproducibility repository. It
contains original project code together with material adapted from
third-party open-source repositories (`BNSL-QA-PYTHON`, GPL-2.0;
`tldks-2020`, Apache-2.0). Full licence and attribution information:
[LICENSE.md](LICENSE.md), [NOTICE.md](NOTICE.md),
[THIRD_PARTY_LICENSES/](THIRD_PARTY_LICENSES/).
