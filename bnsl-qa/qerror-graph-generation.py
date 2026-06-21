import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import sys
import os
import re
from datetime import datetime
from matplotlib.ticker import FixedLocator, FixedFormatter

# Input handling
pairs_file = sys.argv[1]
card_file = sys.argv[2]

sa_files = []
sqa_files = []

with open(pairs_file, "r") as file:
    for line in file:
        parts = line.strip().split()
        if len(parts) == 2:
            sa_files.append(parts[0])
            sqa_files.append(parts[1])


def parse_metadata(fname):
    base = os.path.basename(fname)
    dataset_match = re.search(r'results_(.*?)_SA', base) or re.search(r'results_(.*?)_SQA', base)
    dataset = dataset_match.group(1) if dataset_match else "WetGrass_variance_zero"
    # Matches _Method_Trials_Reads_
    numbers = re.findall(r'_(?:SA|SQA)_(\d+)_(\d+)_', base)
    if numbers:
        trials, reads = numbers[0]
        return dataset.upper(), trials, reads
    return dataset.upper(), "Unknown", "Unknown"


fig, ax = plt.subplots(figsize=(10, 6))

sa_blues = ["#084594", "#2171b5", "#6baed6"]
sqa_purples = ["#4a148c", "#7b1fa2", "#ab47bc"]

max_queries = 0
final_dataset_name = ""
final_trials = ""

for i, (sa_f, sqa_f) in enumerate(zip(sa_files, sqa_files)):
    dataset, trials, sa_reads = parse_metadata(sa_f)
    _, _, sqa_reads = parse_metadata(sqa_f)
    final_dataset_name, final_trials = dataset, trials

    sa_df = pd.read_csv(sa_f)
    sqa_df = pd.read_csv(sqa_f)

    # Calculate sorted medians across 30 trials
    sa_q = np.sort(sa_df.groupby('query_sql')['q_error'].median().values)
    sqa_q = np.sort(sqa_df.groupby('query_sql')['q_error'].median().values)

    # Standardize predictions (perfect = 1.0)
    sa_q = np.maximum(sa_q, 1.0)
    sqa_q = np.maximum(sqa_q, 1.0)

    x = np.arange(1, len(sa_q) + 1)
    max_queries = max(max_queries, len(sa_q))

    ax.plot(x, sa_q, marker='o', color=sa_blues[i % 3], label=f"SA - {sa_reads} Reads - {trials} Trials")
    ax.plot(x, sqa_q, marker='s', linestyle='--', color=sqa_purples[i % 3],
            label=f"SQA - {sqa_reads} Reads - {trials} Trials")

# BNSL / Postgres Reference
card_df = pd.read_csv(card_file)


def q_error_calc(est, true):
    return np.sort(np.maximum(np.maximum(est, 1) / np.maximum(true, 1), np.maximum(true, 1) / np.maximum(est, 1)))


bn_q = q_error_calc(card_df["bn_est_cardinality"], card_df["true_cardinality"])
pg_q = q_error_calc(card_df["pg_est_cardinality"], card_df["true_cardinality"])

x_bench = np.arange(1, len(bn_q) + 1)
ax.plot(x_bench, bn_q, marker='^', color='orange', label="BNSL")
ax.plot(x_bench, pg_q, marker='x', color='grey', label="Postgres")

# Professional Y-Axis (1*10^0, 2*10^0, etc.)
ax.set_yscale('log')
ticks = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000]
tick_labels = [r"$1 \cdot 10^0$", r"$2 \cdot 10^0$", r"$5 \cdot 10^0$",
               r"$1 \cdot 10^1$", r"$2 \cdot 10^1$", r"$5 \cdot 10^1$",
               r"$1 \cdot 10^2$", r"$2 \cdot 10^2$", r"$5 \cdot 10^2$",
               r"$1 \cdot 10^3$", r"$2 \cdot 10^3$", r"$5 \cdot 10^3$"]

ax.yaxis.set_major_locator(FixedLocator(ticks))
ax.yaxis.set_major_formatter(FixedFormatter(tick_labels))

ax.set_xticks(range(1, max_queries + 1))
ax.set_xlabel("Query Index")
ax.set_ylabel("Q-Error")
ax.set_title(f"Sorted Q-Errors for {final_dataset_name}")
ax.grid(True, which="both", linestyle="--", alpha=0.3)
ax.legend(fontsize='small', loc='upper left')

plt.tight_layout()
plt.savefig(f"qerror_sorted_qerror.png", dpi=300)
plt.show()
