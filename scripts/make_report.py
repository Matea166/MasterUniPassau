#!/usr/bin/env python3
import datetime
import html
import os

import pandas as pd

REPO_ROOT = os.environ.get("REPO_ROOT", "/workspace")
RESULTS_ROOT = os.path.join(REPO_ROOT, "results")

EXPERIMENTS = [
    ("wetgrass_100", "E1: WetGrass, N = 100"),
    ("wetgrass_10000", "E2: WetGrass, N = 10,000"),
    ("nhanes", "E3: NHANES, N = 2,278"),
    ("market_basket_100", "E4: Market Basket, N = 100"),
    ("market_basket_10000", "E5: Market Basket, N = 10,000"),
    ("random_control", "E6: Random-structure robustness check"),
]

CSS = """
body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 2rem auto;
       max-width: 1200px; padding: 0 1rem; color: #1c1e21; }
h1 { border-bottom: 3px solid #2980b9; padding-bottom: .3rem; }
h2 { margin-top: 2.5rem; border-bottom: 1px solid #ccc; padding-bottom: .2rem; }
h3 { margin-bottom: .3rem; }
.meta { color: #666; font-size: .9rem; }
.pane { overflow-x: auto; }
table { border-collapse: collapse; font-size: .85rem; width: 100%; }
th, td { border: 1px solid #ddd; padding: .3rem .5rem; text-align: right; }
th { background: #f5f6f7; }
td:first-child, th:first-child { text-align: left; }
img { max-width: 100%; border: 1px solid #ddd; margin: .5rem 0; }
img.fig-medium { max-width: 620px; display: block; }
.missing { color: #c0392b; font-style: italic; }
.note { background: #fdf6e3; border-left: 4px solid #f1c40f; padding: .6rem 1rem;
        margin: 1rem 0; font-size: .9rem; }
details { margin: 1rem 0; }
summary { cursor: pointer; font-weight: 600; }
.queries { margin-top: .5rem; }
.queries th, .queries td { text-align: left; vertical-align: top; }
.queries td:nth-child(2) { font-family: monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
"""


def table_html(csv_path, float_format=None):
    if not os.path.isfile(csv_path):
        return '<p class="missing">not available</p>'
    df = pd.read_csv(csv_path)
    if {"sql", "reason"}.issubset(df.columns):
        df = df.drop(columns=["sql", "reason"])
    if float_format is None:
        float_format = lambda value: f"{value:.3f}"
    return df.to_html(index=False, border=0, na_rep="", float_format=float_format)


def pretty_table_name(fname):
    base = fname[:-4]
    parts = base.split("_")
    number = f"{parts[1]}.{parts[2].lstrip('0') or '0'}"
    rest = " ".join(parts[3:]).replace("qerror", "q-error")
    return f"Table {number}: {rest}", number


def experiment_section(exp, title):
    repro_dir = os.path.join(RESULTS_ROOT, exp, "reproduced_tables")
    parts = [f"<h2>{html.escape(title)}</h2>"]
    files = []
    if os.path.isdir(repro_dir):
        files = sorted(fname for fname in os.listdir(repro_dir) if fname.endswith(".csv"))
    if not files:
        parts.append('<p class="missing">Results not generated yet.</p>')
    for fname in files:
        title, _ = pretty_table_name(fname)
        parts.append(f"<h3>{html.escape(title)}</h3>")
        parts.append(f'<div class="pane">{table_html(os.path.join(repro_dir, fname))}</div>')
        parts.append(f'<p><a href="{exp}/reproduced_tables/{fname}">Download CSV</a></p>')

    figure = os.path.join(RESULTS_ROOT, exp, "figure_6_1_sorted_qerror.png")
    if os.path.isfile(figure):
        parts.append(
            "<h3>Sorted clamped q-error profiles</h3>"
            '<p class="meta">Per-query clamped q-errors of the stable SA and SQA '
            "estimates and the baselines, sorted per estimator.</p>"
            f'<img class="fig-medium" src="{exp}/figure_6_1_sorted_qerror.png" '
            'alt="Sorted q-error profiles">')

    combined = os.path.join(RESULTS_ROOT, exp, "combined_results.png")
    if os.path.isfile(combined):
        parts.append(
            "<h3>Comparison chart (headline configuration)</h3>"
            '<p class="meta">Per-query estimates of all estimators for the '
            "headline configuration.</p>"
            f'<img src="{exp}/combined_results.png" alt="Grouped bar chart">')

    return "\n".join(parts)


def tpcds_section():
    exp = "tpcds_store_sales"
    exp_dir = os.path.join(RESULTS_ROOT, exp)
    tables = os.path.join(exp_dir, "reproduced_tables")
    parts = ["<h2>E7: TPC-DS Store Sales, N = 10,000</h2>",
             "<p>Eight attributes and 20 fixed single-table queries. "
             "Tree and annealing use the same coarse groups; PostgreSQL uses "
             "the raw data with ordinary ANALYZE statistics. "
             "SA/SQA values use the stable-estimate aggregation described above.</p>"]
    if not os.path.isfile(os.path.join(tables, "cardinality_estimates.csv")):
        parts.append('<p class="missing">TPC-DS results not generated yet.</p>')
        return "\n".join(parts)
    for filename, title in [("solver_settings.csv", "Annealing settings"),
                            ("qerror_summary.csv", "Clamped q-error summary"),
                            ("cardinality_estimates.csv", "Estimates and q-errors by query")]:
        path = os.path.join(tables, filename)
        parts.append(f"<h3>{title}</h3>")
        if filename == "cardinality_estimates.csv":
            parts.append('<p class="meta">Query IDs, SQL and selection reasons are retained in the CSV.</p>')
        rendered = table_html(path)
        parts.append(f'<div class="pane">{rendered}</div>')
        parts.append(f'<p><a href="{exp}/reproduced_tables/{filename}">Download CSV</a></p>')
    if os.path.isfile(os.path.join(exp_dir, "combined_results.png")):
        parts.append('<h3>Comparison chart (headline configuration)</h3>'
                     f'<img src="{exp}/combined_results.png" alt="TPC-DS grouped bar chart">')
    return "\n".join(parts)


def query_appendix():
    parts = []
    for dataset, title in [("wetgrass", "WetGrass (100 and 10,000 rows)"),
                           ("nhanes", "NHANES"),
                           ("market_basket", "Market Basket (100 and 10,000 rows; random control)"),
                           ("tpcds_store_sales", "TPC-DS Store Sales")]:
        path = os.path.join(REPO_ROOT, "workloads", dataset + ".csv")
        if not os.path.isfile(path):
            continue
        queries = pd.read_csv(path)[["query_id", "sql"]]
        queries["sql"] = queries["sql"].str.replace(
            r"(?is)^.*?\bWHERE\s+", "", regex=True).str.rstrip("; \t\r\n")
        queries.columns = ["Query ID", "Condition"]
        parts.append(
            f"<details><summary>{html.escape(title)} — {len(queries)} queries</summary>"
            f'<div class="pane queries">{queries.to_html(index=False, border=0)}</div>'
            "</details>")
    if not parts:
        return ""
    return ('<h2 id="queries">Appendix: query workloads</h2>'
            '<p>Expand a dataset to see its query conditions. Query IDs match '
            'the result tables within each dataset.</p>' + "\n".join(parts))


def main():
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    sections = [experiment_section(*e) for e in EXPERIMENTS]
    sections.append(tpcds_section())
    appendix = query_appendix()

    body = f"""<meta charset="utf-8">
<title>AnnealBN-CE Reproduction Report</title>
<style>{CSS}</style>
<h1>AnnealBN-CE Reproduction Report</h1>
<p class="meta">Generated {stamp}. Tables and figures show the results of this run.
Tables include only configurations executed in this run.</p>
{'<p><a href="#queries">Query appendix</a></p>' if appendix else ''}
<div class="note">
<p><strong>Metric convention for this run: clamped q-error.</strong>
For scoring only, both the estimate and true count are floored at 1 before
their ratio is calculated. The original counts are retained. A score of 1
does not necessarily mean an exact prediction: exact-match percentages
compare the original counts with absolute tolerance 1e-9. Metrics use CSV
precision before display rounding; stable SA/SQA estimates retain the
two-decimal modal grouping and use the upper-median original value within
the selected group.</p>
<p>SA and SQA are stochastic solvers, so structures and estimates can vary
between runs.</p>
</div>
{''.join(sections)}
{appendix}
"""

    out = os.path.join(RESULTS_ROOT, "index.html")
    os.makedirs(RESULTS_ROOT, exist_ok=True)
    with open(out, "w") as f:
        f.write(body)
    print(f"Report written to {out}")


if __name__ == "__main__":
    main()
