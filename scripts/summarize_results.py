#!/usr/bin/env python3
"""Builds reproduced versions of the thesis result tables from the raw
outputs in results/<experiment>/, mirroring the column layout of the frozen
reference CSVs in original_results/ so the two can be compared side by side
(scripts/make_report.py renders the comparison as results/index.html).

Inputs per experiment (written by scripts/run_*.sh):
  estimates/estimates_<SOLVER>_T<T>_R<R>.csv  query_sql + one column per learned graph
  qerrors/qerrors_<SOLVER>_T<T>_R<R>.csv      per-graph, per-query q-errors
  chowliu_pg_final.csv                        true, Chow-Liu and PostgreSQL estimates
Random control:
  final_queries_cardinality.csv               query_sql + one column per random matrix

Outputs: results/<experiment>/reproduced_tables/table_*.csv with the same
file names as their originals in original_results/.
"""

import os
import re
import sys
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, NullFormatter, ScalarFormatter

import pandas as pd

REPO_ROOT = os.environ.get("REPO_ROOT", "/workspace")
RESULTS_ROOT = os.path.join(REPO_ROOT, "results")
CONFIG_DIR = os.path.join(REPO_ROOT, "config")

# experiment -> thesis table numbers per table kind
TABLE_NUMBERS = {
    "wetgrass_100": {"estimates": "6_03", "qerror": "6_04"},
    "wetgrass_10000": {"estimates": "6_05", "qerror": "6_06"},
    "nhanes": {"estimates": "6_08", "qerror": "6_09"},
    "market_basket_100": {
        "estimates": "6_10", "qerror": "6_11",
        "read_variation": "6_12", "trial_variation": "6_13",
    },
    "market_basket_10000": {
        "estimates": "6_15", "qerror": "6_16",
        "read_variation": "6_17", "trial_variation": "6_18",
    },
}

# Annealing reference rows of the Table 6.14 random-structure comparison:
# the first stable settings of the Market Basket N=100 experiment.
RANDOM_CHECK_REFS = [("SA", 30, 250), ("SQA", 30, 100)]

EXACT_TOL = 1e-9


def parse_env(path):
    cfg = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            cfg[key.strip()] = value.strip().strip('"')
    return cfg


def normalize_query(q):
    """Same join key as bnsl/merge_csv_logic.py."""
    if not isinstance(q, str):
        return q
    match = re.search(r"WHERE\s+(.*)", q, re.IGNORECASE)
    key = match.group(1) if match else q
    key = key.lower()
    key = "".join(key.split()).replace(";", "")
    key = key.replace("'", "").replace('"', "")
    key = key.replace(".0", "")
    return key


def qerror(est, true):
    """Same convention as bnsl-qa/qerror_calculation.sh for zero values."""
    est, true = float(est), float(true)
    if est == 0 or true == 0:
        return max(est, true)
    return max(est / true, true / est)


def load_truth(exp_dir):
    path = os.path.join(exp_dir, "chowliu_pg_final.csv")
    if not os.path.isfile(path):
        return None
    df = pd.read_csv(path)
    df["join_key"] = df["query_sql"].apply(normalize_query)
    return df


def graph_columns(df):
    return [c for c in df.columns if c != "query_sql" and c != "join_key"]


def load_estimates(exp_dir, solver, trials, reads):
    path = os.path.join(exp_dir, "estimates", f"estimates_{solver}_T{trials}_R{reads}.csv")
    if not os.path.isfile(path):
        return None
    df = pd.read_csv(path)
    df["join_key"] = df["query_sql"].apply(normalize_query)
    return df


def modal_estimate(row, cols):
    """The estimate produced by most learned structures (the thesis's
    'stable' value); ties resolved by the median of the tied values."""
    values = [round(float(row[c]), 2) for c in cols]
    counts = Counter(values)
    top = max(counts.values())
    tied = sorted(v for v, n in counts.items() if n == top)
    return tied[len(tied) // 2]


def fmt_pct(x, decimals=1):
    return f"{x:.{decimals}f}%"


def write_table(exp_dir, number, kind, df):
    out_dir = os.path.join(exp_dir, "reproduced_tables")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"table_{number}_{kind}.csv")
    df.to_csv(out, index=False)
    print(f"  wrote {os.path.relpath(out, RESULTS_ROOT)}")


def stable_estimates(truth, est_df):
    cols = graph_columns(est_df)
    merged = truth.merge(est_df, on="join_key", how="left", suffixes=("", "_est"))
    matched = int(merged[cols[0]].notna().sum()) if cols else 0
    if matched < len(truth) and len(est_df) == len(truth):
        # Some datasets phrase the same workload differently per pipeline
        # (e.g. NHANES: raw values in the solver queries vs encoded bins in
        # the Chow-Liu queries), so the text join fails. The workload order
        # is fixed and identical across pipelines, so align by position.
        est_pos = est_df.reset_index(drop=True)
        return [modal_estimate(row, cols) for _, row in est_pos.iterrows()]
    return [
        modal_estimate(row, cols) if pd.notna(row[cols[0]]) else None
        for _, row in merged.iterrows()
    ]


def make_sorted_qerror_figure(exp_dir, truth, sa_vals, sqa_vals):
    """Reproduces thesis Figure 6.1 (sorted q-error profiles, Market Basket
    N = 100) from this run's data: per-query q-errors of the stable SA/SQA
    estimates and of the deterministic baselines, each sorted ascending and
    plotted by query rank. SA and SQA typically overlap because both produce
    the same stable cardinality pattern; SQA is drawn dashed so the overlap
    stays visible."""
    series = [
        ("SA", sa_vals, "#2a78d6", "o", "-"),
        ("SQA", sqa_vals, "#eb6834", "s", "--"),
        ("Classical baseline", truth["bn_est_cardinality"].tolist(), "#1baf7a", "^", "-"),
        ("PostgreSQL", truth["pg_est_cardinality"].tolist(), "#eda100", "D", "-"),
    ]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    n = len(truth)
    for label, estimates, color, marker, linestyle in series:
        qerrs = sorted(
            qerror(est, t)
            for est, t in zip(estimates, truth["true_cardinality"])
            if est is not None
        )
        ax.plot(range(1, len(qerrs) + 1), qerrs, color=color, marker=marker,
                linestyle=linestyle, linewidth=2, markersize=6, label=label)
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(FixedLocator([1, 2, 5, 10]))
    ax.yaxis.set_major_formatter(ScalarFormatter())
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xticks(range(1, n + 1))
    ax.set_xlabel("Sorted query rank")
    ax.set_ylabel("q-error")
    ax.set_title("Sorted q-error")
    ax.legend(loc="upper left", frameon=False)
    ax.grid(True, which="major", linewidth=0.4, alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out = os.path.join(exp_dir, "figure_6_1_sorted_qerror.png")
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"  wrote {os.path.relpath(out, RESULTS_ROOT)}")


def summarize_experiment(exp, cfg):
    exp_dir = os.path.join(RESULTS_ROOT, exp)
    truth = load_truth(exp_dir)
    if truth is None:
        print(f"  {exp}: no chowliu_pg_final.csv — skipped")
        return

    numbers = TABLE_NUMBERS[exp]
    ht, hr = cfg["HEADLINE_TRIALS"], cfg["HEADLINE_READS"]
    sa = load_estimates(exp_dir, "SA", ht, hr)
    sqa = load_estimates(exp_dir, "SQA", ht, hr)

    # --- cardinality estimates (Tables 6.3 / 6.5 / 6.8 / 6.10 / 6.15) ---
    if sa is not None and sqa is not None:
        rows = []
        sa_vals = stable_estimates(truth, sa)
        sqa_vals = stable_estimates(truth, sqa)
        for i, (_, t) in enumerate(truth.iterrows()):
            rows.append({
                "query": f"Q{i + 1}",
                "true_cardinality": t["true_cardinality"],
                "sa_estimate": sa_vals[i],
                "sqa_estimate": sqa_vals[i],
                "classical_baseline": round(float(t["bn_est_cardinality"]), 2),
                "postgresql": t["pg_est_cardinality"],
            })
        write_table(exp_dir, numbers["estimates"], "cardinality_estimates", pd.DataFrame(rows))

        # --- q-error summary (Tables 6.4 / 6.6 / 6.9 / 6.11 / 6.16) ---
        summary = []
        for label, estimates in [
            ("SA stable", sa_vals),
            ("SQA stable", sqa_vals),
            ("Classical baseline", truth["bn_est_cardinality"].tolist()),
            ("PostgreSQL", truth["pg_est_cardinality"].tolist()),
        ]:
            qerrs = [
                qerror(est, t)
                for est, t in zip(estimates, truth["true_cardinality"])
                if est is not None
            ]
            if not qerrs:
                continue
            s = pd.Series(qerrs)
            summary.append({
                "estimator": label,
                "min_qerror": f"{s.min():.3f}",
                "median_qerror": f"{s.median():.3f}",
                "max_qerror": f"{s.max():.3f}",
                "exact_queries": fmt_pct(100.0 * (s <= 1 + EXACT_TOL).mean()),
            })
        write_table(exp_dir, numbers["qerror"], "qerror_summary", pd.DataFrame(summary))

        # Thesis Figure 6.1 belongs to the Market Basket N=100 experiment
        if exp == "market_basket_100":
            make_sorted_qerror_figure(exp_dir, truth, sa_vals, sqa_vals)

    # --- read / trial variation (Tables 6.12 / 6.13 / 6.17 / 6.18) ---
    if "read_variation" in numbers:
        sweeps = [
            ("read_variation", "reads",
             [(cfg["READ_SWEEP_TRIALS"], r) for r in cfg["READ_SWEEP"].split()]),
            ("trial_variation", "trials",
             [(t, cfg["TRIAL_SWEEP_READS"]) for t in cfg["TRIAL_SWEEP"].split()]),
        ]
        for kind, varying, pairs in sweeps:
            rows = []
            for solver in ("SA", "SQA"):
                for trials, reads in pairs:
                    est = load_estimates(exp_dir, solver, trials, reads)
                    if est is None:
                        continue
                    cols = graph_columns(est)
                    merged = truth.merge(est, on="join_key", how="left")
                    cell_qerrs, distinct_per_query = [], []
                    for _, row in merged.iterrows():
                        values = [round(float(row[c]), 2) for c in cols]
                        distinct_per_query.append(len(set(values)))
                        cell_qerrs.extend(qerror(v, row["true_cardinality"]) for v in values)
                    s = pd.Series(cell_qerrs)
                    rows.append({
                        "method": solver,
                        varying: reads if varying == "reads" else trials,
                        "unique_matrices": len(cols),
                        "max_distinct_per_query": max(distinct_per_query),
                        "median_qerror": f"{s.median():.3f}",
                        "exact_estimates": fmt_pct(100.0 * (s <= 1 + EXACT_TOL).mean()),
                    })
            if rows:
                write_table(exp_dir, numbers[kind], kind + "_summary", pd.DataFrame(rows))


def summarize_random_control():
    exp_dir = os.path.join(RESULTS_ROOT, "random_control")
    final_csv = os.path.join(exp_dir, "final_queries_cardinality.csv")
    if not os.path.isfile(final_csv):
        print("  random_control: no final_queries_cardinality.csv — skipped")
        return

    # True cardinalities and annealing reference rows come from the Market
    # Basket N=100 experiment (Table 6.14 compares against its first stable
    # annealing settings).
    mb_dir = os.path.join(RESULTS_ROOT, "market_basket_100")
    truth = load_truth(mb_dir)
    if truth is None:
        print("  random_control: market_basket_100 results missing — skipped")
        return

    mb_cfg = parse_env(os.path.join(CONFIG_DIR, "market_basket_100.env"))
    rows = []

    for solver, trials, reads in RANDOM_CHECK_REFS:
        est = load_estimates(mb_dir, solver, trials, reads)
        used = (trials, reads)
        if est is None:
            used = (mb_cfg["HEADLINE_TRIALS"], mb_cfg["HEADLINE_READS"])
            est = load_estimates(mb_dir, solver, *used)
        if est is None:
            continue
        rows.append(structure_row(f"{solver}, R = {used[1]}, T = {used[0]}", truth, est))

    rng = pd.read_csv(final_csv)
    rng["join_key"] = rng["query_sql"].apply(normalize_query)
    rows.append(structure_row("Random structures", truth, rng))

    df = pd.DataFrame(rows)
    write_table(exp_dir, "6_14", "random_structure_check", df)


def structure_row(label, truth, est_df):
    cols = graph_columns(est_df)
    merged = truth.merge(est_df, on="join_key", how="left")
    vectors = set()
    cell_qerrs = []
    for c in cols:
        vectors.add(tuple(round(float(v), 2) for v in merged[c]))
        cell_qerrs.extend(
            qerror(v, t) for v, t in zip(merged[c], merged["true_cardinality"])
        )
    s = pd.Series(cell_qerrs)
    return {
        "structure_source": label,
        "structures": len(cols),
        "distinct_ce_vectors": len(vectors),
        "median_qerror": f"{s.median():.2f}",
        "max_qerror": f"{s.max():.2f}",
        "exact_estimates": fmt_pct(100.0 * (s <= 1 + EXACT_TOL).mean(), 2),
    }


def main():
    ran_any = False
    print("Summarizing reproduced results:")
    for exp in TABLE_NUMBERS:
        cfg_path = os.path.join(CONFIG_DIR, f"{exp}.env")
        if os.path.isdir(os.path.join(RESULTS_ROOT, exp)):
            summarize_experiment(exp, parse_env(cfg_path))
            ran_any = True
    if os.path.isdir(os.path.join(RESULTS_ROOT, "random_control")):
        summarize_random_control()
        ran_any = True
    if not ran_any:
        print("  no experiment outputs found under results/ — run scripts/run_*.sh first")
        sys.exit(1)


if __name__ == "__main__":
    main()
