# AnnealBN-CE

Research code for a planned submission to the [BTW 2027 Student Program](https://btw2027.gi.de/calls/student-program),
extending a [master's thesis at the University of Passau](docs/Master%20Thesis.pdf).
The experiments compare cardinality estimates from annealing-learned Bayesian
networks, a tree baseline and PostgreSQL on fixed single-table workloads.

Structure learning uses simulated annealing (SA) and simulated quantum annealing
(SQA). The tree retains the normalized mutual information implementation from
[tldks-2020](https://github.com/MaxHalford/tldks-2020). PostgreSQL uses ordinary
statistics after `ANALYZE`.

Optional [QAOA experiments](docs/QUANTUM.md) use Qiskit Aer, with a separate
IBM hardware sampling path. They are not part of the default reproduction run.

## Run the experiments

Install and start Docker Desktop. Python and PostgreSQL run inside Docker.

```bash
git clone --branch btw2027 https://github.com/Matea166/MasterUniPassau.git
cd MasterUniPassau
QUICK=0 ./reproduce_all.sh
```

On Windows, run `.\reproduce_all.bat` from the cloned folder with `QUICK=0`.
See the [usage guide](docs/USAGE.md#running-experiments) for platform commands
and individual experiments.

The default run recreates this project's Docker database volume. Set `FRESH=0`
to keep the volume; experiment tables are still reloaded. Allow several hours
for the full run. On macOS, keep the machine awake with:

```bash
caffeinate -i env QUICK=0 ./reproduce_all.sh
```

For a smaller workflow check:

```bash
QUICK=1 ./reproduce_all.sh
```

Quick mode reduces the WetGrass, NHANES and Market Basket configuration grids
and the random-structure check. TPC-DS uses the same fixed settings in both modes:
SA 20 trials × 100 reads; SQA 10 trials × 1,000 reads.

## Data and results

| Dataset | Rows | Modeled attributes |
|---|---|---|
| WetGrass | 100 and 10,000 | 4 |
| NHANES | 2,278 | 4 |
| Market Basket | 100 and 10,000 | 6 |
| TPC-DS `store_sales` sample | 10,000 | 8 |

Each dataset has [20 queries](workloads/). WetGrass and Market Basket are generated
with fixed settings; NHANES and TPC-DS CSVs are included. No dataset download is
needed for a normal run. The TPC-DS experiment uses a research sample and custom
queries; it is not an official TPC-DS benchmark result.

Open `results/index.html` after a run. It contains estimates, clamped q-error
summaries and comparison charts, with CSV downloads. Logs and per-structure
estimates are stored under `results/<experiment>/`.

See the usage guide for [data and grouping](docs/USAGE.md#datasets),
[metrics](docs/USAGE.md#metrics) and [output files](docs/USAGE.md#outputs).
Saved PostgreSQL measurements and input hashes are in [reference_results/](reference_results/).

## Checks

```bash
docker compose run --build --rm --no-deps app python -m unittest discover -s tests -v
```

The expanded workflow is awaiting full end-to-end validation. SA and SQA are
stochastic, so structures and estimates can vary between runs.

## Licence and sources

The project includes code adapted from
[BNSL-QA-python](https://github.com/massimo-rizzoli/BNSL-QA-python) and
[tldks-2020](https://github.com/MaxHalford/tldks-2020).
See [LICENSE.md](LICENSE.md), [NOTICE.md](NOTICE.md) and
[THIRD_PARTY_LICENSES/](THIRD_PARTY_LICENSES/) for attribution and licence terms.
