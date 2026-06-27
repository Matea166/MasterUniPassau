## 1. Preparing the Datasets

This repository uses two aligned representations for each dataset:

| Representation            | Location                    | Purpose                                                                                                                                           |
| ------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Solver TXT representation | `bnsl-qa/qa-datasets/`      | Input format required by the `bnslqa` structure-learning solver. The values are finite integer states.                                            |
| CSV tabular relation      | `bnsl/datasets/data/`       | Input used for cardinality estimation, PostgreSQL queries, Chow--Liu estimation, and Bayesian-network fitting after a structure has been learned. |
| PostgreSQL table          | Docker PostgreSQL container | Required for executing the query workloads and obtaining PostgreSQL planner estimates.                                                            |

This separation is important because the annealing-based structure-learning component works on integer-encoded finite-state data, while the cardinality-estimation components operate on tabular relation attributes and values.

### 1.1. Clone the Repository and Start the Docker Environment

Clone the repository and enter the project directory:

```bash
git clone https://github.com/Matea166/MasterUniPassau.git
cd MasterUniPassau
```

Build and start the Docker environment:

```bash
docker compose up -d --build
```

Enter the application container:

```bash
docker compose exec app bash
```

All commands below assume that they are executed inside the application container, where the repository is mounted at:

```bash
/workspace
```

The Docker setup starts a Python application container and a PostgreSQL container. PostgreSQL is required because the cardinality-estimation workflow compares the Bayesian-network-based estimates with PostgreSQL estimates and also uses database tables for the query workloads.

> Note: the Docker setup exposes PostgreSQL on host port `5432`. If that port is already used on your machine, stop the conflicting local service or change the port mapping in `docker-compose.yml`.

---

## 1.2. Directory Overview for Dataset Preparation

The dataset-preparation workflow uses the following directories and files:

```text
bnsl-qa/
├── problems/                 # JSON problem definitions for synthetic BN data
│   └── WetGrass.json
├── qa-datasets/              # Solver TXT files used by bnslqa
├── Market_Basket_synthetic_data_gen.py
├── Nhanes_csv_to_txt.py
└── movie_link_csv_to_txt.py

bnsl/
└── datasets/
    ├── data/                 # CSV relations used for CE and PostgreSQL import
    ├── txt_to_csv.py          # Converts WetGrass TXT solver data to CSV
    ├── csv_to_db.py           # Imports CSV data into PostgreSQL
    ├── csv_to_db_NHANES.py    # Imports NHANES CSV data into PostgreSQL
    ├── db_table_to_csv.py     # Exports a PostgreSQL table to CSV
    └── gen_synthetic_csv_market_basket.py

docker/
└── postgres/
    ├── init/
    │   └── 01-init-nhanes-and-imdb.sql
    ├── wetgrass/
    │   └── WetGrass.sql
    ├── MarketBasket/
    │   └── MarketBasket.sql
    └── import_imdb.sh
```

The general rule is:

1. Prepare or generate a CSV relation in `bnsl/datasets/data/`.
2. Prepare or generate the corresponding solver TXT file in `bnsl-qa/qa-datasets/`.
3. Load the CSV relation into PostgreSQL using an appropriate database schema.
4. Ensure that all downstream scripts use the same dataset name, table name, and file paths.

---

## 1.3. WetGrass Dataset

WetGrass is the controlled synthetic Bayesian-network dataset. It is defined by the JSON file:

```text
bnsl-qa/problems/WetGrass.json
```

The JSON specification defines:

* the variables: `Cloud`, `Sprinkler`, `Rain`, and `WetGrass`;
* the states of each variable;
* the parent sets;
* the conditional probability tables;
* the reference adjacency matrix;
* the topological order used during generation.

The WetGrass Bayesian network and conditional probability tables are also provided as a figure:

```text
bnsl-qa/images/WetGrass.pdf
```

For GitHub README display, it is recommended to export the PDF as a PNG and save it as:

```text
bnsl-qa/images/WetGrass.png
```

### 1.3.1. Generate the WetGrass Solver TXT File

Enter the `bnsl-qa` directory:

```bash
cd /workspace/bnsl-qa
```

Generate an expected WetGrass dataset:

```bash
python -m bnslqa generate problems/WetGrass.json --size 100 --expected --name WetGrass
```

This creates:

```text
bnsl-qa/qa-datasets/WetGrass.txt
```

> Important: the default WetGrass converter expects the solver file to be named
> `bnsl-qa/qa-datasets/WetGrass.txt`. Therefore, the safest command is to keep
> `--name WetGrass`. If another name is used, for example `WetGrass_10000` or
> `WetGrass_sampled_100`, the `input_txt_file` variable in
> `bnsl/datasets/txt_to_csv.py` must be updated before converting the TXT file
> to CSV.

The `--size` parameter controls the intended dataset size. For example, to generate a larger dataset:

```bash
python -m bnslqa generate problems/WetGrass.json --size 10000 --expected --name WetGrass_10000
```

The `--name` parameter controls the output file name. If `--name WetGrass` is used, the generated file is:

```text
qa-datasets/WetGrass.txt
```

If another name is used, the corresponding converter scripts must be updated to read that file. In particular, `bnsl/datasets/txt_to_csv.py` must point to the actual generated TXT file through its `input_txt_file` variable.

### 1.3.2. Expected versus Non-Expected Generation

With `--expected`, the generator creates a deterministic expected-value dataset. For each complete variable configuration, the probability is computed from the JSON conditional probability tables, multiplied by the requested dataset size, and rounded to obtain the number of generated rows for that configuration. This is useful for controlled variance-zero experiments.

Because of rounding, the final number of generated rows may not be exactly equal to the requested `--size`.

Without `--expected`, the generator samples rows randomly from the Bayesian network distribution. In that case, the dataset contains sampling variance, but the number of generated rows is exactly the requested size.

Example without expected-value generation:

```bash
python -m bnslqa generate problems/WetGrass.json --size 100 --name WetGrass_sampled_100
```

This creates:

```text
bnsl-qa/qa-datasets/WetGrass_sampled_100.txt
```

### 1.3.3. Convert the WetGrass TXT File to CSV

The solver TXT file is required for structure learning, but the cardinality-estimation workflow also needs a CSV relation. To convert the WetGrass TXT file to CSV, go to the `bnsl/datasets` directory:

```bash
cd /workspace/bnsl/datasets
```

Before running the converter, check the configuration at the top of:

```text
bnsl/datasets/txt_to_csv.py
```

For the default WetGrass setup, it should point to the generated TXT file and the desired CSV output:

```python
input_txt_file = "../../bnsl-qa/qa-datasets/WetGrass.txt"
output_csv_file = "data/WetGrass_variance_zero.csv"

columns = ["Cloud", "Sprinkler", "Rain", "WetGrass"]

state_maps = {
    "Cloud": {0: "t", 1: "f"},
    "Sprinkler": {0: "on", 1: "off"},
    "Rain": {0: "t", 1: "f"},
    "WetGrass": {0: "t", 1: "f"}
}
```

Run the converter:

```bash
python txt_to_csv.py
```

This writes the CSV relation to:

```text
bnsl/datasets/data/WetGrass_variance_zero.csv
```

If a different TXT file name was used during generation, update `input_txt_file`. If a different CSV name is desired, update `output_csv_file`.

### 1.3.4. Create the WetGrass PostgreSQL Database and Table

The suggested WetGrass schema is stored in:

```text
docker/postgres/wetgrass/WetGrass.sql
```

It creates a database named `wetgrass` and a table named `wetgrass_data`:

```sql
CREATE DATABASE wetgrass;

\c wetgrass;

CREATE TABLE wetgrass_data (
    cloud CHAR(1),
    sprinkler VARCHAR(3),
    rain CHAR(1),
    wetgrass CHAR(1)
);
```

Create the database and table from the repository root:

```bash
cd /workspace
PGPASSWORD=postgres psql -h postgres -U postgres -d postgres -f docker/postgres/wetgrass/WetGrass.sql
```

This schema is a suggested starting point. If you generate several WetGrass datasets, for example one with `N=100` and another with `N=10000`, you can either:

* create separate databases, such as `wetgrass_100` and `wetgrass_10000`; or
* create separate tables inside one database, such as `wetgrass_data_100` and `wetgrass_data_10000`.

In either case, the Python import and cardinality-estimation scripts must use the same database and table names.

### 1.3.5. Import the WetGrass CSV into PostgreSQL

The CSV import script is:

```text
bnsl/datasets/csv_to_db.py
```

Before running it, check and update the configuration:

```python
DB_NAME = "wetgrass"
DB_USER = "postgres"
DB_PASSWORD = "postgres"
DB_HOST = "postgres"
DB_PORT = "5432"

CSV_FILE = "data/WetGrass_variance_zero.csv"
TABLE_NAME = "wetgrass_data"
```

> Important: the CSV file configured here must be the same file produced by
> `txt_to_csv.py`. For the expected WetGrass dataset used in the thesis, this is
> normally `data/WetGrass_variance_zero.csv`. If `csv_to_db.py` still points to
> `data/WetGrass_variance_non_zero.csv`, update it before running the import.

Also ensure that the `INSERT` statement matches the table columns:

```python
insert_query = f"""
INSERT INTO {TABLE_NAME} (
    cloud, sprinkler, rain, wetgrass
)
VALUES (%s, %s, %s, %s)
"""
```

Then run:

```bash
cd /workspace/bnsl/datasets
python csv_to_db.py
```

After this step, the WetGrass dataset is available in all three required forms:

```text
bnsl-qa/qa-datasets/WetGrass.txt
bnsl/datasets/data/WetGrass_variance_zero.csv
PostgreSQL: wetgrass.wetgrass_data
```

---

## 1.4. Adding a New JSON-Based Bayesian-Network Problem

To add a new synthetic Bayesian-network problem, create a JSON file in:

```text
bnsl-qa/problems/
```

For example:

```text
bnsl-qa/problems/NewProblem.json
```

The JSON file should follow the same structure as `WetGrass.json`:

```json
{
  "name": "NewProblem",
  "variables": {
    "A": {
      "states": ["0", "1"],
      "parents": [],
      "cpt": [0.5]
    },
    "B": {
      "states": ["0", "1"],
      "parents": ["A"],
      "cpt": [
        [0.8],
        [0.2]
      ]
    }
  },
  "solution": [
    [0, 1],
    [0, 0]
  ],
  "toporder": [
    "A",
    "B"
  ]
}
```

The main fields are:

| Field       | Meaning                                                                                                               |
| ----------- | --------------------------------------------------------------------------------------------------------------------- |
| `name`      | Name of the problem written into the solver TXT file.                                                                 |
| `variables` | Variable definitions, including states, parents, and CPTs.                                                            |
| `states`    | Possible states of each variable.                                                                                     |
| `parents`   | Parent variables in the Bayesian network.                                                                             |
| `cpt`       | Conditional probability table. For binary variables, the probability of the last state is computed as the complement. |
| `solution`  | Reference adjacency matrix. Entry `[i][j] = 1` means an edge from variable `i` to variable `j`.                       |
| `toporder`  | Optional fixed topological order used during generation.                                                              |

Generate the solver TXT file:

```bash
cd /workspace/bnsl-qa
python -m bnslqa generate problems/NewProblem.json --size 1000 --expected --name NewProblem
```

This creates:

```text
bnsl-qa/qa-datasets/NewProblem.txt
```

To integrate the new problem into the full cardinality-estimation pipeline, also create or adapt:

1. a TXT-to-CSV converter, based on `bnsl/datasets/txt_to_csv.py`;
2. a CSV output file in `bnsl/datasets/data/`;
3. a PostgreSQL schema file in `docker/postgres/`;
4. a CSV-to-database import configuration;
5. the corresponding cardinality-estimation script and query workload.

The important requirement is that the TXT encoding, CSV values, database table columns, and query predicates all use a consistent variable order and state mapping.

---

## 1.5. NHANES Dataset

NHANES is a real health-survey dataset. The full CSV file is already available in:

```text
bnsl/datasets/data/NHANES_age_prediction.csv
```

The Docker initialisation file also creates a PostgreSQL database named `nhanes`, a table named `nhanes_data`, imports the CSV, and runs `ANALYZE`.

The relevant SQL file is:

```text
docker/postgres/init/01-init-nhanes-and-imdb.sql
```

The table contains the following columns:

```text
seqn, age_group, ridageyr, riagendr, paq605,
bmxbmi, lbxglu, diq010, lbxglt, lbxin
```

### 1.5.1. Generate the NHANES Solver TXT File

The solver TXT conversion script is:

```text
bnsl-qa/Nhanes_csv_to_txt.py
```

Run:

```bash
cd /workspace/bnsl-qa
python Nhanes_csv_to_txt.py
```

The script reads:

```text
../bnsl/datasets/data/NHANES_age_prediction.csv
```

It keeps a selected subset of columns, bins `BMXBMI` into four medical categories, encodes categorical variables as integer states, and writes a solver TXT file to `bnsl-qa/qa-datasets/`.

The script also writes mapping files to:

```text
bnsl-qa/qa-datasets/mappings/
```

These mapping files are important because they document how original categorical values were translated into solver-side integer states.

If reproducing the exact thesis run, use the existing thesis TXT file:

```text
bnsl-qa/qa-datasets/NHANES_age_prediction_subset.txt
```

If regenerating the TXT file, make sure that the output file name in `Nhanes_csv_to_txt.py` matches the file expected by the solver dispatch and cardinality-estimation scripts.

### 1.5.2. Import or Re-Import NHANES into PostgreSQL

For a fresh Docker volume, NHANES is imported automatically during PostgreSQL initialisation.

If the database already exists and the Docker volume was not recreated, the initialisation script will not run again automatically. In that case, either recreate the PostgreSQL volume or use:

```text
bnsl/datasets/csv_to_db_NHANES.py
```

Before running it, check:

```python
DB_NAME = "nhanes"
CSV_FILE = "data/NHANES_age_prediction.csv"
TABLE_NAME = "nhanes_data"
```

Then run:

```bash
cd /workspace/bnsl/datasets
python csv_to_db_NHANES.py
```

---

## 1.6. Market Basket Dataset

The Market Basket dataset is a synthetic binary transaction dataset. Each row represents a transaction, and each column indicates whether an item is present (`1`) or absent (`0`).

The CSV generator is:

```text
bnsl/datasets/gen_synthetic_csv_market_basket.py
```

It uses the item columns:

```text
Beer, Bread, Cola, Diapers, Eggs, Milk
```

### 1.6.1. Generate the Market Basket CSV File

Run:

```bash
cd /workspace/bnsl/datasets
python gen_synthetic_csv_market_basket.py
```

By default, the script generates 100 rows and writes:

```text
bnsl/datasets/data/DataMining_MarketBasket_100.csv
```

To generate a different dataset size, edit:

```python
num_rows = 100
csv_filename = "data/DataMining_MarketBasket_100.csv"
```

For example, for 10000 rows:

```python
num_rows = 10000
csv_filename = "data/DataMining_MarketBasket_10000.csv"
```

### 1.6.2. Create the Market Basket PostgreSQL Database and Table

The suggested schema is:

```text
docker/postgres/MarketBasket/MarketBasket.sql
```

It creates a database named `market_basket` and a table named `transactions`:

```sql
CREATE DATABASE market_basket;

\c market_basket

CREATE TABLE transactions (
    beer INTEGER,
    bread INTEGER,
    cola INTEGER,
    diapers INTEGER,
    eggs INTEGER,
    milk INTEGER
);
```

Run the schema file from the repository root:

```bash
cd /workspace
PGPASSWORD=postgres psql -h postgres -U postgres -d postgres -f docker/postgres/MarketBasket/MarketBasket.sql
```

### 1.6.3. Import the Market Basket CSV into PostgreSQL

The general CSV import script is:

```text
bnsl/datasets/csv_to_db.py
```

For Market Basket, update its configuration:

```python
DB_NAME = "market_basket"
CSV_FILE = "data/DataMining_MarketBasket_100.csv"
TABLE_NAME = "transactions"
```

Update the `INSERT` statement so that it matches the Market Basket table:

```python
insert_query = f"""
INSERT INTO {TABLE_NAME} (
    beer, bread, cola, diapers, eggs, milk
)
VALUES (%s, %s, %s, %s, %s, %s)
"""
```

Then run:

```bash
cd /workspace/bnsl/datasets
python csv_to_db.py
```

If a different dataset size or file name is used, update `CSV_FILE` accordingly.

### 1.6.4. Generate the Market Basket Solver TXT File

The solver TXT generator is:

```text
bnsl-qa/Market_Basket_synthetic_data_gen.py
```

Run:

```bash
cd /workspace/bnsl-qa
python Market_Basket_synthetic_data_gen.py
```

By default, it reads:

```text
../bnsl/datasets/data/DataMining_MarketBasket_100.csv
```

and writes:

```text
qa-datasets/MarketBasket100.txt
```

If you generate a different CSV file, update:

```python
csv_filename = "../bnsl/datasets/data/DataMining_MarketBasket_100.csv"
output_file = "qa-datasets/MarketBasket100.txt"
```

For example, for 10000 rows:

```python
csv_filename = "../bnsl/datasets/data/DataMining_MarketBasket_10000.csv"
output_file = "qa-datasets/MarketBasket10000.txt"
```

---

## 1.7. Movie Link Dataset

The Movie Link dataset is derived from the IMDB/JOB data. It is optional because it requires downloading and importing the IMDB data archive.

### 1.7.1. Import the IMDB Data into PostgreSQL

Run the IMDB import script from the repository root:

```bash
cd /workspace
bash docker/postgres/import_imdb.sh
```

The script downloads the IMDB archive, extracts it into:

```text
imdb_data/extracted/
```

and imports the tables into the PostgreSQL database:

```text
imdb
```

The imported tables include, among others:

```text
movie_link, movie_info, movie_keyword, title, name, cast_info
```

### 1.7.2. Export the `movie_link` Table to CSV

The script for exporting a PostgreSQL table to CSV is:

```text
bnsl/datasets/db_table_to_csv.py
```

Before running it, set:

```python
TABLE = "movie_link"
```

Then run:

```bash
cd /workspace/bnsl/datasets
python db_table_to_csv.py
```

This writes:

```text
bnsl/datasets/data/movie_link.csv
```

### 1.7.3. Generate the Movie Link Solver TXT File

The solver TXT conversion script is:

```text
bnsl-qa/movie_link_csv_to_txt.py
```

Run:

```bash
cd /workspace/bnsl-qa
python movie_link_csv_to_txt.py
```

The script reads:

```text
../bnsl/datasets/data/movie_link.csv
```

It drops the primary key column `id`, caps high-cardinality categorical values using `MAX_STATES`, encodes the remaining values as integer states, and writes:

```text
qa-datasets/MovieLink_Capped_3vars.txt
```

The parameter:

```python
MAX_STATES = 15
```

controls how many frequent values are preserved per column before the remaining values are grouped into an `Other` state. This is important because high-cardinality attributes can make the solver representation too large and may cause numerical problems during QUBO construction.

If you change `MAX_STATES`, rerun the script and keep the printed translation dictionaries. They define how solver-side integer states map back to the original categorical values.

---

## 1.8. Checklist Before Running Cardinality Estimation

Before moving to the cardinality-estimation step, check that the following files and database objects exist.

### WetGrass

```text
bnsl-qa/qa-datasets/WetGrass.txt
bnsl/datasets/data/WetGrass_variance_zero.csv
PostgreSQL database: wetgrass
PostgreSQL table: wetgrass_data
```

### NHANES

```text
bnsl/datasets/data/NHANES_age_prediction.csv
bnsl-qa/qa-datasets/NHANES_age_prediction_subset.txt
PostgreSQL database: nhanes
PostgreSQL table: nhanes_data
```

### Market Basket

```text
bnsl/datasets/data/DataMining_MarketBasket_100.csv
bnsl-qa/qa-datasets/MarketBasket100.txt
PostgreSQL database: market_basket
PostgreSQL table: transactions
```

### Movie Link

```text
imdb_data/extracted/movie_link.csv
bnsl/datasets/data/movie_link.csv
bnsl-qa/qa-datasets/MovieLink_Capped_3vars.txt
PostgreSQL database: imdb
PostgreSQL table: movie_link
```

The file names used here should match the names expected by the solver dispatch scripts and the cardinality-estimation scripts. If a dataset name, CSV file name, TXT file name, database name, or table name is changed, update the corresponding configuration variables in the relevant Python scripts before running the next stage.

One correction before the copy-paste text: in the raw Chow--Liu CSV, `est_selectivity` is **not** the PostgreSQL estimate. In the code, it is the Bayesian-network selectivity/probability. PostgreSQL estimates are added later by `cardinality_benchmarks.sh` in the `_final.csv` file as `pg_est_cardinality`. ([GitHub][1])

I also checked that the correct script name is `cardinality_benchmarks.sh` with **plural** `benchmarks`, and that `dispatch.sh` creates the three output areas described below. ([GitHub][2])

## 2. Running Cardinality Estimates

After the datasets have been prepared, the repository supports two cardinality-estimation pipelines:

1. **AnnealBN-CE**, which uses adjacency matrices learned by simulated annealing or simulated quantum annealing.
2. **Chow--Liu baseline**, implemented in the `bnsl` directory and used as the classical Bayesian-network benchmark.

Both pipelines assume that the relevant CSV relation has already been created in `bnsl/datasets/data/` and that the corresponding PostgreSQL table has already been imported.

---

## 2.1. AnnealBN-CE Cardinality Estimates

The AnnealBN-CE pipeline is executed from the `bnsl-qa` directory. It starts from a solver TXT file, learns one or more Bayesian-network structures through annealing, fits each learned structure on the corresponding CSV relation, and writes query-level cardinality estimates.

Enter the `bnsl-qa` directory:

```bash
cd /workspace/bnsl-qa
```

Run the interactive dispatch script:

```bash
bash dispatch.sh
```

The script guides the execution interactively. On a first run, select:

```text
Run solver now
```

Then select:

1. the solver TXT dataset from `bnsl-qa/qa-datasets/`;
2. the annealing solver, either `SA` or `SQA`;
3. the number of trials;
4. the number of annealing reads;
5. the cardinality-estimation script matching the selected dataset.

The available cardinality-estimation scripts are stored in:

```text
bnsl-qa/cardinality_estimation/
```

Use the script that corresponds to the selected dataset:

| Dataset       | Cardinality-estimation script                                    |
| ------------- | ---------------------------------------------------------------- |
| WetGrass      | `cardinality_estimation/cardinality_estimation_WetGrass.py`      |
| NHANES        | `cardinality_estimation/cardinality_estimation_NHANES.py`        |
| Market Basket | `cardinality_estimation/cardinality_estimation_Market_Basket.py` |
| Movie Link    | `cardinality_estimation/cardinality_estimation_Movie_Link.py`    |

Before running a dataset, check that the selected cardinality-estimation script reads the correct CSV file. The solver TXT file is used for structure learning, but the cardinality-estimation script separately loads the CSV relation with `pd.read_csv(...)` or `pd.read_csv(dataset_path)`. Therefore, the CSV path in the selected script must match the dataset prepared in `bnsl/datasets/data/`.

For example, the WetGrass script should load:

```python
df = pd.read_csv("../bnsl/datasets/data/WetGrass_variance_zero.csv")
```

The Market Basket script should load the intended Market Basket CSV file, for example:

```python
df = pd.read_csv("../bnsl/datasets/data/DataMining_MarketBasket_100.csv")
```

If the dataset size or file name was changed during dataset preparation, update this path before running the dispatch pipeline.

### 2.1.1. Trials and Reads

The dispatch script asks for two solver parameters:

| Parameter | Meaning                                                                                                                                                                                        |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Trials    | Number of independent solver executions for the selected dataset, solver, and read setting. Trials are used to observe whether repeated runs produce the same or different learned structures. |
| Reads     | Number of annealing reads passed to the solver in each trial. A read is one solver attempt to sample a candidate binary assignment for the QUBO problem.                                       |

For example, if `trials = 5` and `reads = 100`, the script runs the selected solver five independent times, and each solver execution uses 100 annealing reads.

The selected solver returns binary assignments for the QUBO formulation. These assignments are decoded into adjacency matrices. Each unique adjacency matrix represents one learned Bayesian-network structure.

If both `SA` and `SQA` should be evaluated, run `dispatch.sh` once for `SA` and then run it again for `SQA`.

---

## 2.2. Reusing Previous Unique Matrices

After at least one solver run has been completed, `dispatch.sh` can also reuse previously generated unique matrices. In that case, select:

```text
Use previous unique matrices
```

This mode is useful when the solver has already been run and only the cardinality-estimation step should be repeated. The script asks for a previous `unique_adjacency_matrix.txt` file and then applies the selected cardinality-estimation script to the stored matrices.

This avoids rerunning the annealing solver and makes it possible to regenerate graph visualisations or cardinality CSV files from existing learned structures.

---

## 2.3. AnnealBN-CE Output Structure

The dispatch pipeline writes all AnnealBN-CE outputs to:

```text
bnsl-qa/dispatch_output/
```

This directory contains three main output areas:

```text
dispatch_output/
├── cardinality_estimation_outputs/
├── results/
└── solver_outputs/
```

### 2.3.1. Per-Graph Cardinality Outputs

Per-graph cardinality outputs are stored in:

```text
dispatch_output/cardinality_estimation_outputs/
```

The outputs are separated by solver:

```text
dispatch_output/cardinality_estimation_outputs/
├── SA-results/
└── SQA-results/
```

Each run creates a timestamped folder. For example:

```text
dispatch_output/cardinality_estimation_outputs/SA-results/
└── SA-results_WetGrass_2_2026-06-27_15-37-18/
    ├── Graph_1.png
    └── graph_1_cardinality.csv
```

For SQA, if two unique adjacency matrices are found, the output may look like:

```text
dispatch_output/cardinality_estimation_outputs/SQA-results/
└── SQA-results_WetGrass_1_2026-06-27_15-42-10/
    ├── Graph_1.png
    ├── graph_1_cardinality.csv
    ├── Graph_2.png
    └── graph_2_cardinality.csv
```

The folder name has the following form:

```text
<SOLVER>-results_<DATASET>_<READS>_<TIMESTAMP>
```

For example:

```text
SA-results_WetGrass_2_2026-06-27_15-37-18
```

means:

| Part                  | Meaning                                          |
| --------------------- | ------------------------------------------------ |
| `SA-results`          | Simulated annealing cardinality outputs          |
| `WetGrass`            | Dataset name inferred from the selected TXT file |
| `2`                   | Number of annealing reads                        |
| `2026-06-27_15-37-18` | Timestamp in `YYYY-MM-DD_HH-MM-SS` format        |

Each `Graph_<id>.png` file visualises one learned Bayesian-network structure. Each `graph_<id>_cardinality.csv` file contains the cardinality estimates produced by that specific graph.

The per-graph CSV files have the format:

```text
query_sql,estimated_cardinality
```

For example:

```text
query_sql,estimated_cardinality
SELECT * FROM wetgrass_data WHERE wetgrass = 'f',17.46000
SELECT * FROM wetgrass_data WHERE cloud = 't' AND wetgrass = 't',21.36000
```

These files are useful for inspecting the estimates of each learned Bayesian network separately.

### 2.3.2. Final Combined AnnealBN-CE Results

The combined AnnealBN-CE result files are stored in:

```text
dispatch_output/results/
```

For example:

```text
dispatch_output/results/
├── final_queriescardinality_SA_WetGrass_2_2026-06-27_15-37-18.csv
└── final_queriescardinality_SQA_WetGrass_1_2026-06-27_15-42-10.csv
```

Each final CSV merges the per-graph cardinality estimates into one file. The first column contains the query, and each following column contains the estimates of one learned graph:

```text
query_sql,Graph_1.png,Graph_2.png
```

For example:

```text
SELECT * FROM wetgrass_data WHERE wetgrass = 'f',18.0,20.862
SELECT * FROM wetgrass_data WHERE cloud = 't' AND wetgrass = 't',21.0,16.824
```

The graph columns correspond to the graph visualisations in `cardinality_estimation_outputs/`. For example, `Graph_1.png` in the final CSV corresponds to the file `Graph_1.png` in the matching run folder.

This final file is the main AnnealBN-CE output used for comparing the cardinality estimates produced by the unique learned Bayesian-network structures.

### 2.3.3. Solver Outputs and Diagnostics

Solver outputs are stored in:

```text
dispatch_output/solver_outputs/
```

The outputs are separated by solver:

```text
dispatch_output/solver_outputs/
├── SA/
└── SQA/
```

Each solver run creates a timestamped folder. For example:

```text
dispatch_output/solver_outputs/SA/
└── SA_Matrix_WetGrass_2_2_2026-06-27_15-37-18/
    ├── adjacency_matrix.txt
    └── unique_adjacency_matrix.txt
```

The folder name has the following form:

```text
<SOLVER>_Matrix_<DATASET>_<TRIALS>_<READS>_<TIMESTAMP>
```

For example:

```text
SA_Matrix_WetGrass_2_2_2026-06-27_15-37-18
```

means:

| Part                  | Meaning                                   |
| --------------------- | ----------------------------------------- |
| `SA_Matrix`           | Solver output from simulated annealing    |
| `WetGrass`            | Dataset name                              |
| `2`                   | Number of trials                          |
| `2`                   | Number of reads                           |
| `2026-06-27_15-37-18` | Timestamp in `YYYY-MM-DD_HH-MM-SS` format |

The file:

```text
adjacency_matrix.txt
```

stores the complete solver-side output for all trials. This file is intended for transparency and debugging. It may include duplicate solution matrices if the solver returns the same structure more than once.

Depending on the dataset and solver run, `adjacency_matrix.txt` may contain:

```text
QUBO Matrix
Expected adjacency matrix
Solution adjacency matrix
Expected solution
expY
expX
Minimum found
minY
minX
minY/expY
Method
Number of reads
Occurrences of minX
Found minX at read
QUBO formulation time
Annealing/Execution time
```

The file:

```text
unique_adjacency_matrix.txt
```

contains only the deduplicated adjacency matrices extracted from `adjacency_matrix.txt`. Each line represents one unique learned Bayesian-network structure. This is the file used by the cardinality-estimation step, so identical structures are not evaluated repeatedly.

---

## 2.4. Chow--Liu Baseline Cardinality Estimates

The Chow--Liu baseline is executed from the `bnsl` directory. This pipeline learns a tree-structured Bayesian network from the selected CSV relation and compares its cardinality estimates with the true cardinalities and PostgreSQL planner estimates.

Enter the `bnsl` directory:

```bash
cd /workspace/bnsl
```

Run the benchmark script:

```bash
bash cardinality_benchmarks.sh
```

The script is interactive. It first lists the available PostgreSQL databases and asks which database should be used for the comparison. Then it asks which Python cardinality-estimation script should be executed.

The Chow--Liu cardinality-estimation scripts are stored in:

```text
bnsl/cardinality_estimation/
```

The relevant scripts are:

| Dataset       | Chow--Liu script                                                 |
| ------------- | ---------------------------------------------------------------- |
| WetGrass      | `cardinality_estimation/cardinality_estimation_wetgrass.py`      |
| NHANES        | `cardinality_estimation/cardinality_estimation_NHANES_robust.py` |
| Market Basket | `cardinality_estimation/cardinality_estimation_market_basket.py` |
| Movie Link    | `cardinality_estimation/cardinality_estimation_movie_link.py`    |

Before running a script, check that its CSV configuration matches the prepared dataset. In most scripts, the CSV file is selected through variables such as:

```python
CSV_FILE = "WetGrass_variance_zero"
DATA_PATH = f"datasets/data/{CSV_FILE}.csv"
```

The file name must match a CSV file in:

```text
bnsl/datasets/data/
```

For example, if the prepared CSV file is:

```text
bnsl/datasets/data/WetGrass_variance_zero.csv
```

then the script should use:

```python
CSV_FILE = "WetGrass_variance_zero"
```

If a different dataset size or file name is used, update `CSV_FILE` before running the benchmark.

The selected PostgreSQL database must also match the SQL queries inside the selected cardinality-estimation script. For example:

| Dataset       | Expected PostgreSQL database | Expected table  |
| ------------- | ---------------------------- | --------------- |
| WetGrass      | `wetgrass`                   | `wetgrass_data` |
| NHANES        | `nhanes`                     | `nhanes_data`   |
| Market Basket | `market_basket`              | `transactions`  |
| Movie Link    | `imdb`                       | `movie_link`    |

For the Movie Link experiment, select the `imdb` database. In this repository, the Movie Link workload uses only the `movie_link` table from the imported IMDB/JOB data.

---

## 2.5. Chow--Liu Output Files

The Chow--Liu benchmark writes its results to:

```text
bnsl/card_results/
```

For each run, two CSV files are produced:

```text
result_<DATASET>_<TIMESTAMP>.csv
result_<DATASET>_<TIMESTAMP>_final.csv
```

For example:

```text
card_results/
├── result_WetGrass_variance_zero_20260627_163617.csv
└── result_WetGrass_variance_zero_20260627_163617_final.csv
```

The non-final CSV is the raw output of the selected Chow--Liu cardinality-estimation script. It contains the query, the true cardinality, the Chow--Liu estimate, and the Bayesian-network selectivity.

For the standard scripts, the raw file has the structure:

```text
query_sql,true_cardinality,bn_est_cardinality,est_selectivity
```

The meaning of the columns is:

| Column               | Meaning                                                             |
| -------------------- | ------------------------------------------------------------------- |
| `query_sql`          | Query workload entry                                                |
| `true_cardinality`   | Cardinality obtained directly from the CSV relation                 |
| `bn_est_cardinality` | Chow--Liu Bayesian-network cardinality estimate                     |
| `est_selectivity`    | Selectivity/probability estimated by the Chow--Liu Bayesian network |

The `_final.csv` file is created by `cardinality_benchmarks.sh`. It adds the PostgreSQL planner estimate by running `EXPLAIN (FORMAT JSON)` for each query against the selected PostgreSQL database.

The final file has the structure:

```text
query_sql,true_cardinality,bn_est_cardinality,pg_est_cardinality
```

The meaning of the columns is:

| Column               | Meaning                                 |
| -------------------- | --------------------------------------- |
| `query_sql`          | Query workload entry                    |
| `true_cardinality`   | True cardinality                        |
| `bn_est_cardinality` | Chow--Liu cardinality estimate          |
| `pg_est_cardinality` | PostgreSQL planner cardinality estimate |

The `_final.csv` file is the main Chow--Liu baseline output used for comparison with PostgreSQL and AnnealBN-CE.

---

## 2.6. Checklist Before Running Cardinality Estimation

Before running either pipeline, check the following:

1. The required CSV file exists in `bnsl/datasets/data/`.
2. The required solver TXT file exists in `bnsl-qa/qa-datasets/` if AnnealBN-CE is being run.
3. The PostgreSQL database and table have been created and populated.
4. The selected cardinality-estimation script loads the correct CSV file.
5. The SQL queries inside the selected script use the correct PostgreSQL table name.
6. The selected dataset, solver output, and cardinality-estimation script refer to the same variable order and state mapping.

For AnnealBN-CE, also check that the selected adjacency matrix has the same number of variables as the selected cardinality-estimation script expects. For example, a WetGrass matrix has four variables and must be used with the WetGrass cardinality-estimation script, not with the Market Basket or NHANES scripts.

For Chow--Liu, check that the selected PostgreSQL database corresponds to the selected script. For example, if `cardinality_estimation_wetgrass.py` is selected, the PostgreSQL database should be `wetgrass`, and the table referenced in the script should be `wetgrass_data`.

[1]: https://raw.githubusercontent.com/Matea166/MasterUniPassau/master/bnsl/cardinality_estimation/cardinality_estimation_wetgrass.py "raw.githubusercontent.com"
[2]: https://raw.githubusercontent.com/Matea166/MasterUniPassau/master/bnsl-qa/dispatch.sh "raw.githubusercontent.com"

## 3. Optional Random-Structure Robustness Check

This section is optional and is mainly intended for validation. It is not part of the standard dataset-preparation or cardinality-estimation routine. The purpose is to compare the AnnealBN-CE estimates against a random-structure control.

The q-error evaluation shows how accurate the cardinality estimates of the annealing-learned structures are, but it does not show by itself whether this accuracy is specific to the structure-learning step. The random-structure robustness check is therefore used as a negative control. It tests whether randomly generated admissible Bayesian-network structures can produce similar cardinality estimates.

In this repository, the random-structure check is implemented in:

```text
bnsl-qa/RNG_matrix.sh
```

The script generates random acyclic adjacency matrices and evaluates them with the same cardinality-estimation scripts used by AnnealBN-CE. The only intended difference is the origin of the structure:

| Structure type           | Origin                                                |
| ------------------------ | ----------------------------------------------------- |
| AnnealBN-CE structure    | Learned from the QUBO formulation using `SA` or `SQA` |
| Random-control structure | Randomly generated acyclic adjacency matrix           |

The random matrices are generated with the same maximum-parent restriction used in the thesis experiments. Each generated matrix represents a candidate Bayesian-network structure. The cardinality-estimation script then fits the parameters on the same tabular relation and evaluates the same query workload.

---

### 3.1. Run the Random-Structure Pipeline

Enter the `bnsl-qa` directory:

```bash
cd /workspace/bnsl-qa
```

Run the random-structure pipeline:

```bash
bash RNG_matrix.sh
```

The script displays the following menu:

```text
==== RNG MATRIX PIPELINE ====
1) Generate matrices
2) Run cardinality estimation
3) Exit
```

On a first run, choose:

```text
1) Generate matrices
```

The script then asks for:

```text
Number of variables:
Number of matrices:
```

The number of variables must match the number of variables in the dataset being checked. This is the number of columns used by the corresponding solver TXT representation and the corresponding cardinality-estimation script.

For example:

| Dataset                          | Number of variables |
| -------------------------------- | ------------------: |
| WetGrass                         |                   4 |
| Market Basket                    |                   6 |
| Movie Link capped representation |                   3 |

For any new or modified dataset, check the first number in the solver TXT file header or the number of attributes used in the corresponding cardinality-estimation script. Do not use the number of rows as the number of variables.

The number of matrices controls how many random DAG candidates should be generated. For example, choosing `4` variables and `10` matrices creates a file named:

```text
bnsl-qa/RNG_Matrix/matrices/RNG_matrix_10_4.txt
```

The file name has the form:

```text
RNG_matrix_<number_of_requested_matrices>_<number_of_variables>.txt
```

The generator deduplicates the matrices, so the number of unique matrices written to the file may be smaller than the number requested.

---

### 3.2. Run Cardinality Estimation on the Random Matrices

After generating the random matrices, run the same script again if needed:

```bash
bash RNG_matrix.sh
```

Then choose:

```text
2) Run cardinality estimation
```

The script first asks you to select a cardinality-estimation script from:

```text
bnsl-qa/cardinality_estimation/
```

Choose the script that matches the dataset you want to evaluate:

| Dataset       | Cardinality-estimation script                                    |
| ------------- | ---------------------------------------------------------------- |
| WetGrass      | `cardinality_estimation/cardinality_estimation_WetGrass.py`      |
| NHANES        | `cardinality_estimation/cardinality_estimation_NHANES.py`        |
| Market Basket | `cardinality_estimation/cardinality_estimation_Market_Basket.py` |
| Movie Link    | `cardinality_estimation/cardinality_estimation_Movie_Link.py`    |

Then select the random matrix file from:

```text
bnsl-qa/RNG_Matrix/matrices/
```

For example:

```text
RNG_matrix_10_4.txt
```

The script then evaluates every matrix in the selected file with the selected cardinality-estimation script.

Before running this step, check that the selected cardinality-estimation script loads the correct CSV relation and uses the correct database table names in its query workload. This is the same consistency requirement as in the AnnealBN-CE pipeline.

For example, a WetGrass random-structure check should use:

```text
Dataset: WetGrass
Number of variables: 4
Cardinality script: cardinality_estimation/cardinality_estimation_WetGrass.py
CSV relation: ../bnsl/datasets/data/WetGrass_variance_zero.csv
Database table in queries: wetgrass_data
```

A random matrix generated for one dataset must not be evaluated with another dataset's cardinality-estimation script. For example, a 4-variable WetGrass matrix should not be used with the 6-variable Market Basket script.

---

### 3.3. Random-Structure Output Files

The random-structure robustness check writes its outputs to:

```text
bnsl-qa/RNG_Matrix/
```

The generated random matrices are stored in:

```text
bnsl-qa/RNG_Matrix/matrices/
```

For example:

```text
bnsl-qa/RNG_Matrix/matrices/RNG_matrix_10_4.txt
```

The cardinality-estimation outputs are stored in timestamped run folders under:

```text
bnsl-qa/RNG_Matrix/results/
```

For example:

```text
bnsl-qa/RNG_Matrix/results/run_2026-06-27_17-00-03/
```

A run folder may contain files such as:

```text
graph_1_cardinality.csv
Graph_1.png
graph_2_cardinality.csv
Graph_2.png
...
final_queries_cardinality.csv
```

Each `graph_<id>_cardinality.csv` file contains the cardinality estimates produced by one random adjacency matrix.

Each `Graph_<id>.png` file visualises the corresponding random Bayesian-network structure, if graph generation is enabled by the selected cardinality-estimation script.

The file:

```text
final_queries_cardinality.csv
```

combines the per-matrix cardinality estimates into one CSV file. Its structure is:

```text
query_sql,matrix_1,matrix_2,...
```

The first column contains the query workload entry. Each following column contains the estimated cardinalities produced by one random matrix.

---

### 3.4. How to Interpret the Random-Structure Check

The random-structure robustness check should be interpreted as a negative control.

If the random structures produce cardinality estimates and q-errors similar to the AnnealBN-CE structures, then the observed estimation quality cannot be attributed confidently to the annealing-based structure-learning step.

If the AnnealBN-CE structures produce lower median and maximum q-errors than the random structures, this supports the interpretation that the annealing solver finds structures that are useful for the cardinality-estimation task.

The comparison should be made under the same conditions:

1. same tabular relation;
2. same query workload;
3. same cardinality-estimation script;
4. same true cardinalities;
5. same q-error calculation procedure;
6. same number of variables;
7. same maximum-parent restriction.

This ensures that the structure source is the main difference between the AnnealBN-CE result and the random-control result.

---

### 3.5. Checklist for the Robustness Check

Before running the random-structure robustness check, verify the following:

1. The dataset has already been prepared as described in the dataset-preparation section.
2. The CSV relation exists in `bnsl/datasets/data/`.
3. The selected cardinality-estimation script reads the correct CSV file.
4. The SQL queries inside the selected script use the correct table name.
5. The number of variables entered into `RNG_matrix.sh` matches the dataset.
6. The selected random matrix file matches the dataset's number of variables.
7. The selected cardinality-estimation script corresponds to the same dataset.
8. The output file `final_queries_cardinality.csv` is created under `bnsl-qa/RNG_Matrix/results/run_<timestamp>/`.

The random-structure robustness check produces validation outputs only. The generated random matrices should not be treated as learned AnnealBN-CE structures.


