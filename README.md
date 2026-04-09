
# BNSL & BNSL-QA Cardinality Estimation Framework

This repository provides a comprehensive workflow for generating QA datasets, running cardinality estimations, and comparing results between BNSL, BNSL-QA, and PostgreSQL estimates. It also includes tools for calculating Q-errors and generating data visualizations like histograms and graphs.

## Table of Contents
1. [Preparing the Workspace](#1-preparing-the-workspace)
2. [Running Cardinality Estimations](#2-running-cardinality-estimations)
3. [Analysis and Visualization](#3-analysis-and-visualization)

---

## 1. Preparing the Workspace

Before running any estimations, you need to generate and format your dataset.

**Generate a QA Dataset**
To generate a dataset, use the `bnslqa` module. The following command generates a dataset from a JSON problem file:

```bash
python -m bnslqa generate problems/wetGrass.json --size 100 --expected --name WETGRASS
```

**Data Conversion & Database Setup**
Depending on your starting point and requirements, you may need to convert your data files. 

* **TXT to CSV:** To use the generated dataset for cardinality estimation, convert it to a CSV format:
    ```bash
    python bnsl/datasets/txt_to_csv.py
    ```
* **CSV to Database:** To get PostgreSQL estimates, the data must be loaded into a database:
    ```bash
    python bnsl/datasets/csv_to_db.py
    ```
* **CSV to TXT:** If you are starting with a CSV file (e.g., NHANES) and need to generate a text file:
    ```bash
    python bnsl-qa/Nhnes_csv_to_txt.py
    ```

---

## 2. Running Cardinality Estimations

Once your data is prepared and loaded, you can run the solvers and benchmarks.

**BNSL-QA Solution**
To run the cardinality estimation using the BNSL-QA solver, execute the dispatch script. This will output a CSV containing the solver results.

```bash
bash bnslqa/dispatch.sh
```

**BNSL Solution & PostgreSQL Estimate**
To run the standard BNSL cardinality estimation and compare it against the PostgreSQL database estimate, use the benchmark script. This generates a final CSV with both estimates.

```bash
bash bnsl/cardinality_benchmarks.sh
```

**Randomized Matrices Comparison**
If you want to compare your results against randomized matrices, run the following script:

```bash
bash bnsl-qa/RNG_matrix.sh
```

---

## 3. Analysis and Visualization

The repository includes shell scripts to help you visualize the results of your estimations and analyze the errors.

**Generate Histograms**
To merge your results and generate a histogram, use the `merge_results.sh` script. The program is interactive and will prompt you to specify what data you want to display. 

> **Note:** If your input CSV contains more than 4 matrices, the resulting histogram will automatically include standard error bars.

```bash
bash bnsl/merge_results.sh
```

**Calculate Q-Errors and Generate Graphs**
To evaluate the accuracy of the estimations, calculate the Q-errors:

```bash
bash bnsl-qa/qerror_calculation.sh
```

Once the Q-errors are calculated, you can generate a visual Q-error graph:

```bash
bash qerror-graph-generation.sh
```markdown
# BNSL & BNSL-QA Cardinality Estimation Framework

This repository provides a comprehensive workflow for generating QA datasets, running cardinality estimations, and comparing results between BNSL, BNSL-QA, and PostgreSQL estimates. It also includes tools for calculating Q-errors and generating data visualizations like histograms and graphs.

## Table of Contents
1. [Preparing the Workspace](#1-preparing-the-workspace)
2. [Running Cardinality Estimations](#2-running-cardinality-estimations)
3. [Analysis and Visualization](#3-analysis-and-visualization)

---

## 1. Preparing the Workspace

Before running any estimations, you need to generate and format your dataset.

**Generate a QA Dataset**
To generate a dataset, use the `bnslqa` module. The following command generates a dataset from a JSON problem file:

```bash
python -m bnslqa generate problems/wetGrass.json --size 100 --expected --name WETGRASS
```

**Data Conversion & Database Setup**
Depending on your starting point and requirements, you may need to convert your data files. 

* **TXT to CSV:** To use the generated dataset for cardinality estimation, convert it to a CSV format:
    ```bash
    python bnsl/datasets/txt_to_csv.py
    ```
* **CSV to Database:** To get PostgreSQL estimates, the data must be loaded into a database:
    ```bash
    python bnsl/datasets/csv_to_db.py
    ```
* **CSV to TXT:** If you are starting with a CSV file (e.g., NHANES) and need to generate a text file:
    ```bash
    python bnsl-qa/Nhnes_csv_to_txt.py
    ```

---

## 2. Running Cardinality Estimations

Once your data is prepared and loaded, you can run the solvers and benchmarks.

**BNSL-QA Solution**
To run the cardinality estimation using the BNSL-QA solver, execute the dispatch script. This will output a CSV containing the solver results.

```bash
bash bnslqa/dispatch.sh
```

**BNSL Solution & PostgreSQL Estimate**
To run the standard BNSL cardinality estimation and compare it against the PostgreSQL database estimate, use the benchmark script. This generates a final CSV with both estimates.

```bash
bash bnsl/cardinality_benchmarks.sh
```

**Randomized Matrices Comparison**
If you want to compare your results against randomized matrices, run the following script:

```bash
bash bnsl-qa/RNG_matrix.sh
```

---

## 3. Analysis and Visualization

The repository includes shell scripts to help you visualize the results of your estimations and analyze the errors.

**Generate Histograms**
To merge your results and generate a histogram, use the `merge_results.sh` script. The program is interactive and will prompt you to specify what data you want to display. 

> **Note:** If your input CSV contains more than 4 matrices, the resulting histogram will automatically include standard error bars.

```bash
bash bnsl/merge_results.sh
```

**Calculate Q-Errors and Generate Graphs**
To evaluate the accuracy of the estimations, calculate the Q-errors:

```bash
bash bnsl-qa/qerror_calculation.sh
```

Once the Q-errors are calculated, you can generate a visual Q-error graph:

```bash
bash qerror-graph-generation.sh
```
