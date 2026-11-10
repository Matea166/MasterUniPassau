import argparse
import os
from datetime import datetime
from pathlib import Path

import graphviz
import pandas as pd

from bnsl.datasets.tpcds_encoding import (
    DATA_PATH,
    ROOT,
    WORKLOAD_PATH,
    assignments,
    encode,
    load_queries,
    matching_rows,
    tree_data,
    tree_state,
)
from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation


def fit_model(encoded):
    return BayesianNetwork(cl_max_rows=30000).fit(Relation(tree_data(encoded)))


def estimate_probability(model, filters):
    return sum(
        model.p(**{column: tree_state(column, code) for column, code in query.items()})
        for query in assignments(filters)
    )


def main():
    parser = argparse.ArgumentParser()
    csv_name = os.environ.get("CSV_FILE", DATA_PATH.stem)
    parser.add_argument(
        "--input",
        type=Path,
        default=os.environ.get(
            "CE_DATASET_CSV", DATA_PATH.with_name(csv_name + ".csv")
        ),
    )
    parser.add_argument("--workload", type=Path, default=WORKLOAD_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    encoded = encode(pd.read_csv(args.input))
    queries = load_queries(args.workload)
    model = fit_model(encoded)
    output_dir = ROOT / "output_bn"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        dot_file = output_dir / f"{args.input.stem}_bn.dot"
        dot_file.write_text(str(model.to_dot()))
        graphviz.render(
            "dot", "png", str(dot_file), outfile=str(dot_file.with_suffix(".png"))
        )
    except Exception as exc:
        print(f"[Graph] Warning: {exc}")
    results = []
    for query, filters in queries:
        probability = estimate_probability(model, filters)
        results.append(
            {
                "query_sql": query["sql"],
                "true_cardinality": int(matching_rows(encoded, filters).sum()),
                "bn_est_cardinality": probability * len(encoded),
                "est_selectivity": probability,
            }
        )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = (
        args.output
        or ROOT / "bnsl/card_results" / f"result_{args.input.stem}_{timestamp}.csv"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(output, index=False)
    print(f"Results saved to: {output}")


if __name__ == "__main__":
    main()
