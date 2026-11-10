import os
from datetime import datetime

import graphviz
import pandas as pd

from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation
from bnsl.workloads import load_queries


def main():
    csv_file = os.environ.get("CSV_FILE", "WetGrass_variance_zero")
    data_path = f"datasets/data/{csv_file}.csv"
    output_dir = "../output_bn"
    results_dir = "card_results"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)
    df = pd.read_csv(data_path)
    df_raw = df.copy()
    for col in df.columns:
        df[col] = df[col].astype(str)
    relation = Relation(df)
    bn = BayesianNetwork(cl_max_rows=30000).fit(relation)
    bn.update(relation)
    print("\n--- Generating Graph ---")
    try:
        dot_file = os.path.join(output_dir, f"{csv_file}_bn.dot")
        png_file = os.path.join(output_dir, f"{csv_file}_bn.png")
        with open(dot_file, "w") as f:
            f.write(str(bn.to_dot()))
        graphviz.render("dot", "png", dot_file, outfile=png_file)
        print(f"[Graph] Saved to: {png_file}")
    except Exception as e:
        print(f"[Graph] Warning: {e}")
    queries = load_queries("wetgrass", df_raw, df)
    results_log = []
    print("\n--- Running Queries and Logging Results ---")
    for sql, filters in queries:
        subset = df.copy()
        for col, val in filters.items():
            subset = subset[subset[col] == val]
        true_card = len(subset)
        est_prob = bn.p(**filters)
        est_card = est_prob * len(df)
        results_log.append(
            {
                "query_sql": sql,
                "true_cardinality": true_card,
                "bn_est_cardinality": est_card,
                "est_selectivity": est_prob,
            }
        )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"result_{csv_file}_{timestamp}.csv"
    output_path = os.path.join(results_dir, output_filename)
    results_df = pd.DataFrame(results_log)
    results_df.to_csv(output_path, index=False)
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()
