import os
from datetime import datetime

import graphviz
import pandas as pd

from bnsl.datasets.grouping_tpcds import (
    assignments,
    encode,
    tree_data,
    tree_state,
)
from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation
from bnsl.workloads import load_queries


def main():
    csv_file = os.environ.get("CSV_FILE", "TPCDS_store_sales_10000")
    data_path = f"datasets/data/{csv_file}.csv"
    output_dir = "../output_bn"
    results_dir = "card_results"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)
    print(f"--- Loading Data from {data_path} ---")
    df_raw = pd.read_csv(data_path)
    encoded = encode(df_raw)
    df = tree_data(encoded)
    print(f"Total rows in dataset: {len(df)}")
    print(f"Columns: {df.columns.tolist()}")
    print("\n--- Training Bayesian Network ---")
    relation = Relation(df)
    bn = BayesianNetwork(cl_max_rows=30000).fit(relation)
    bn.update(relation)
    print("Bayesian Network training complete.")
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
    queries = load_queries("tpcds_store_sales", df_raw, encoded)
    results_log = []
    print("\n--- Running Queries and Logging Results ---")
    for sql, filters in queries:
        subset = encoded.copy()
        for col, states in filters.items():
            subset = subset[subset[col].isin(states)]
        true_card = len(subset)
        est_prob = sum(
            bn.p(**{col: tree_state(col, code) for col, code in query.items()})
            for query in assignments(filters)
        )
        est_card = est_prob * len(df)
        results_log.append(
            {
                "query_sql": sql,
                "true_cardinality": true_card,
                "bn_est_cardinality": est_card,
                "est_selectivity": est_prob,
            }
        )
        print(f"Query: {sql}")
        print(f" -> True: {true_card} | Est: {est_card:.2f} (Prob: {est_prob:.6f})")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"result_{csv_file}_{timestamp}.csv"
    output_path = os.path.join(results_dir, output_filename)
    results_df = pd.DataFrame(results_log)
    results_df.to_csv(output_path, index=False)
    print(f"\nProcessing Complete. Results saved to: {output_path}")


if __name__ == "__main__":
    main()
