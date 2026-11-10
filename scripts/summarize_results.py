#!/usr/bin/env python3
"""Build common estimate and q-error tables from the current experiment outputs."""

import os
import sys
import math
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, NullFormatter, ScalarFormatter

import pandas as pd
from bnsl.workloads import normalize_query

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


def qerror(est, true):
    est, true = float(est), float(true)
    if not all(math.isfinite(v) and v >= 0 for v in (est, true)):
        raise ValueError("Cardinalities must be finite and non-negative.")
    est, true = max(est, 1.0), max(true, 1.0)
    return max(est / true, true / est)


def exact_estimate(est, true):
    return abs(float(est) - float(true)) <= EXACT_TOL


def load_truth(exp_dir):
    if os.path.exists(os.path.join(exp_dir, ".running")):
        raise ValueError(f"Incomplete experiment: {exp_dir}. Rerun it before building the report.")
    path = os.path.join(exp_dir, "chowliu_pg_final.csv")
    if not os.path.isfile(path):
        return None
    df = pd.read_csv(path)
    df["join_key"] = df["query_sql"].apply(normalize_query)
    return df


def graph_columns(df):
    return [c for c in df.columns if c != "query_sql" and c != "join_key"]


def load_estimates(exp_dir, solver, trials, reads):
    manifest = os.path.join(exp_dir, "configurations.csv")
    if os.path.isfile(manifest):
        configurations = pd.read_csv(manifest)
        selected = configurations["solver"].eq(solver)
        selected &= configurations["trials"].eq(int(trials))
        selected &= configurations["reads"].eq(int(reads))
        if not selected.any():
            return None
    path = os.path.join(exp_dir, "estimates", f"estimates_{solver}_T{trials}_R{reads}.csv")
    if not os.path.isfile(path):
        return None
    df = pd.read_csv(path)
    df["join_key"] = df["query_sql"].apply(normalize_query)
    return df


def modal_estimate(row, cols):
    values = [float(row[c]) for c in cols]
    counts = Counter(round(v, 2) for v in values)
    top = max(counts.values())
    tied = sorted(v for v, n in counts.items() if n == top)
    selected = tied[len(tied) // 2]
    originals = sorted(v for v in values if round(v, 2) == selected)
    return originals[len(originals) // 2]


def fmt_pct(x, decimals=1):
    return f"{x:.{decimals}f}%"


def write_table(exp_dir, number, kind, df):
    out_dir = os.path.join(exp_dir, "reproduced_tables")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"table_{number}_{kind}.csv")
    df.to_csv(out, index=False)
    print(f"  wrote {os.path.relpath(out, RESULTS_ROOT)}")


def merge_estimates(truth, est_df):
    for label, frame in [("Baseline", truth), ("Estimates", est_df)]:
        keys = frame["join_key"]
        if frame.empty or keys.isna().any() or keys.eq("").any():
            raise ValueError(f"{label}: missing queries in the result CSV.")
        if keys.duplicated().any():
            raise ValueError(f"{label}: duplicate query keys in the result CSV.")
    if set(truth["join_key"]) != set(est_df["join_key"]):
        raise ValueError("Query mismatch: generate baseline and estimate CSVs using the same original SQL workload.")
    cols = graph_columns(est_df)
    if not cols or est_df[cols].isna().any().any():
        raise ValueError("Missing graph estimates in the result CSV.")
    return truth.merge(est_df, on="join_key", how="left", suffixes=("", "_est"), validate="one_to_one")


def stable_estimates(truth, est_df):
    cols = graph_columns(est_df)
    merged = merge_estimates(truth, est_df)
    return [modal_estimate(row, cols) for _, row in merged.iterrows()]


def workload_truth(truth, dataset):
    workload = pd.read_csv(os.path.join(REPO_ROOT, "workloads", f"{dataset}.csv"))
    workload["join_key"] = workload["sql"].apply(normalize_query)
    ids = workload["query_id"]
    if ids.isna().any() or ids.duplicated().any() or ids.str.strip().eq("").any():
        raise ValueError("Missing or duplicate query IDs.")
    return merge_estimates(workload, truth)


def estimate_tables(truth, sa_vals, sqa_vals):
    per_query = truth[["query_id", "sql", "reason", "true_cardinality"]].copy()
    rows = []
    for key, label, values in [
        ("sa", "SA stable", sa_vals), ("sqa", "SQA stable", sqa_vals),
        ("tree", "Tree baseline", truth["bn_est_cardinality"].tolist()),
        ("postgresql", "PostgreSQL", truth["pg_est_cardinality"].tolist()),
    ]:
        qerrs = pd.Series([qerror(est, true)
                           for est, true in zip(values, truth["true_cardinality"])])
        per_query[f"{key}_estimate"] = values
        per_query[f"{key}_qerror"] = qerrs.tolist()
        exact = sum(exact_estimate(est, true) for est, true in zip(values, truth["true_cardinality"]))
        rows.append({"estimator": label, "queries": len(truth),
                     "min_qerror": qerrs.min(), "median_qerror": qerrs.median(),
                     "p95_qerror": qerrs.quantile(0.95), "max_qerror": qerrs.max(),
                     "exact_queries": fmt_pct(100.0 * exact / len(truth))})
    return per_query, pd.DataFrame(rows)


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
    ax.set_ylabel("Clamped q-error")
    ax.set_title("Sorted clamped q-error")
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
    truth = workload_truth(truth, exp.rsplit("_", 1)[0])

    numbers = TABLE_NUMBERS[exp]
    for kind, number in numbers.items():
        suffix = {"estimates": "cardinality_estimates", "qerror": "qerror_summary"}.get(kind, kind + "_summary")
        previous = os.path.join(exp_dir, "reproduced_tables", f"table_{number}_{suffix}.csv")
        if os.path.isfile(previous):
            os.remove(previous)
    ht, hr = cfg["HEADLINE_TRIALS"], cfg["HEADLINE_READS"]
    sa = load_estimates(exp_dir, "SA", ht, hr)
    sqa = load_estimates(exp_dir, "SQA", ht, hr)
    if sa is None or sqa is None:
        raise ValueError(f"{exp}: missing headline estimates; rerun the experiment.")

    # --- cardinality estimates (Tables 6.3 / 6.5 / 6.8 / 6.10 / 6.15) ---
    if sa is not None and sqa is not None:
        sa_vals = stable_estimates(truth, sa)
        sqa_vals = stable_estimates(truth, sqa)
        per_query, summary = estimate_tables(truth, sa_vals, sqa_vals)
        write_table(exp_dir, numbers["estimates"], "cardinality_estimates", per_query)

        # --- q-error summary (Tables 6.4 / 6.6 / 6.9 / 6.11 / 6.16) ---
        write_table(exp_dir, numbers["qerror"], "qerror_summary", summary)

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
                    merged = merge_estimates(truth, est)
                    cell_qerrs, cell_exact, distinct_per_query = [], [], []
                    for _, row in merged.iterrows():
                        values = [float(row[c]) for c in cols]
                        distinct_per_query.append(len({round(v, 2) for v in values}))
                        cell_qerrs.extend(qerror(v, row["true_cardinality"]) for v in values)
                        cell_exact.extend(exact_estimate(v, row["true_cardinality"]) for v in values)
                    s = pd.Series(cell_qerrs)
                    rows.append({
                        "method": solver,
                        varying: reads if varying == "reads" else trials,
                        "unique_matrices": len(cols),
                        "max_distinct_per_query": max(distinct_per_query),
                        "median_qerror": f"{s.median():.3f}",
                        "exact_estimates": fmt_pct(100.0 * pd.Series(cell_exact).mean()),
                    })
            if rows:
                write_table(exp_dir, numbers[kind], kind + "_summary", pd.DataFrame(rows))


def summarize_random_control():
    exp_dir = os.path.join(RESULTS_ROOT, "random_control")
    if os.path.exists(os.path.join(exp_dir, ".running")):
        raise ValueError("Incomplete random-control experiment. Rerun it before building the report.")
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
    merged = merge_estimates(truth, est_df)
    vectors = set()
    cell_qerrs, cell_exact = [], []
    for c in cols:
        vectors.add(tuple(round(float(v), 2) for v in merged[c]))
        cell_qerrs.extend(
            qerror(v, t) for v, t in zip(merged[c], merged["true_cardinality"])
        )
        cell_exact.extend(
            exact_estimate(v, t) for v, t in zip(merged[c], merged["true_cardinality"])
        )
    s = pd.Series(cell_qerrs)
    return {
        "structure_source": label,
        "structures": len(cols),
        "distinct_ce_vectors": len(vectors),
        "median_qerror": f"{s.median():.2f}",
        "max_qerror": f"{s.max():.2f}",
        "exact_estimates": fmt_pct(100.0 * pd.Series(cell_exact).mean(), 2),
    }


def summarize_tpcds():
    exp_dir = os.path.join(RESULTS_ROOT, "tpcds_store_sales")
    cfg = parse_env(os.path.join(CONFIG_DIR, "tpcds_store_sales.env"))
    truth = load_truth(exp_dir)
    if truth is None:
        raise ValueError("TPC-DS: missing chowliu_pg_final.csv.")
    truth = workload_truth(truth, "tpcds_store_sales")
    estimates = {}
    settings = []
    for solver in ("SA", "SQA"):
        trials, reads = cfg[f"{solver}_TRIALS"], cfg[f"{solver}_READS"]
        est = load_estimates(exp_dir, solver, trials, reads)
        if est is None:
            raise ValueError(f"TPC-DS: missing {solver} estimates for {trials} trials and {reads} reads.")
        estimates[solver.lower()] = stable_estimates(truth, est)
        settings.append({"solver": solver, "trials": int(trials), "reads": int(reads),
                         "unique_structures": len(graph_columns(est))})

    per_query, summary = estimate_tables(truth, estimates["sa"], estimates["sqa"])

    out_dir = os.path.join(exp_dir, "reproduced_tables")
    os.makedirs(out_dir, exist_ok=True)
    for filename, frame in [("cardinality_estimates.csv", per_query),
                            ("qerror_summary.csv", summary),
                            ("solver_settings.csv", pd.DataFrame(settings))]:
        out = os.path.join(out_dir, filename)
        frame.to_csv(out, index=False)
        print(f"  wrote {os.path.relpath(out, RESULTS_ROOT)}")


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
    if os.path.isdir(os.path.join(RESULTS_ROOT, "tpcds_store_sales")):
        summarize_tpcds()
        ran_any = True
    if not ran_any:
        print("  no experiment outputs found under results/ — run scripts/run_*.sh first")
        sys.exit(1)


if __name__ == "__main__":
    main()
