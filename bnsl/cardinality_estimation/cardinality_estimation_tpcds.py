import argparse
import os
from pathlib import Path

import pandas as pd

from bnsl.datasets.tpcds_encoding import (
    DATA_PATH, ROOT, WORKLOAD_PATH, assignments, encode, load_queries,
    matching_rows, tree_data, tree_state,
)
from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation


def fit_model(encoded):
    return BayesianNetwork(cl_max_rows=30000).fit(Relation(tree_data(encoded)))


def estimate_probability(model, filters):
    return sum(model.p(**{column: tree_state(column, code) for column, code in query.items()})
               for query in assignments(filters))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=os.environ.get("CE_DATASET_CSV", DATA_PATH))
    parser.add_argument("--workload", type=Path, default=WORKLOAD_PATH)
    parser.add_argument("--output", type=Path, default=ROOT / "bnsl/card_results/result_TPCDS_store_sales_10000.csv")
    args = parser.parse_args()
    encoded = encode(pd.read_csv(args.input))
    queries = load_queries(args.workload)
    model = fit_model(encoded)
    results = []
    for query, filters in queries:
        probability = estimate_probability(model, filters)
        results.append({"query_id": query["query_id"], "query_sql": query["sql"],
                        "true_cardinality": int(matching_rows(encoded, filters).sum()),
                        "bn_est_cardinality": probability * len(encoded),
                        "est_selectivity": probability})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(args.output, index=False)
    print(f"Results saved to: {args.output}")


if __name__ == "__main__":
    main()
