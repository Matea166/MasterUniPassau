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

The `--size` parameter controls the intended dataset size. For example, to generate a larger dataset:

```bash
python -m bnslqa generate problems/WetGrass.json --size 10000 --expected --name WetGrass_10000
```

The `--name` parameter controls the output file name. If `--name WetGrass` is used, the generated file is:

```text
qa-datasets/WetGrass.txt
```

If another name is used, the corresponding converter scripts must be updated to read that file.

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
