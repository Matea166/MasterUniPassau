import argparse
import ast
import os
from pathlib import Path

import graphviz
import networkx as nx
import numpy as np
import pandas as pd
from pgmpy.estimators import MaximumLikelihoodEstimator
from pgmpy.inference import VariableElimination
from pgmpy.models import DiscreteBayesianNetwork

from bnsl.workloads import load_queries


def load_data(path):
    raw = pd.read_csv(path)
    columns = ["age_group", "BMXBMI", "RIAGENDR", "DIQ010"]
    encoded = raw[columns].copy()
    encoded["BMXBMI"] = pd.cut(
        encoded["BMXBMI"],
        bins=[0, 18.5, 25.0, 30.0, 150.0],
        labels=[0, 1, 2, 3],
        right=False,
    ).astype(int)
    for column in ["age_group", "RIAGENDR", "DIQ010"]:
        encoded[column] = encoded[column].astype("category").cat.codes
    return raw, encoded


def fit_model(encoded, matrix):
    columns = encoded.columns.tolist()
    matrix = np.asarray(matrix)
    size = len(columns)
    if matrix.shape != (size, size) or not np.isin(matrix, [0, 1]).all():
        raise ValueError(f"Expected a {size} by {size} binary adjacency matrix.")
    edges = [(columns[i], columns[j]) for i, j in zip(*np.nonzero(matrix))]
    model = DiscreteBayesianNetwork()
    model.add_nodes_from(columns)
    model.add_edges_from(edges)
    if not nx.is_directed_acyclic_graph(model):
        raise ValueError("Cannot estimate a cyclic graph.")
    model.fit(encoded, estimator=MaximumLikelihoodEstimator)
    model.check_model()
    return model


def estimate_probability(inference, filters):
    result = inference.query(variables=list(filters), evidence={}, show_progress=False)
    return result.get_value(**filters)


def draw_graph(model, output_dir, graph_index):
    try:
        graph = graphviz.Digraph()
        graph.attr(rankdir="TB")
        for column in model.nodes():
            graph.node(
                column, column, shape="ellipse", style="filled", fillcolor="lightblue"
            )
        graph.edges(model.edges())
        graph.render(
            str(output_dir / f"Graph_{graph_index}"), format="png", cleanup=True
        )
    except Exception as exc:
        print(f"[Warning] Could not generate graph: {exc}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=ast.literal_eval)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("graph_index")
    parser.add_argument(
        "--input",
        type=Path,
        default=os.environ.get(
            "CE_DATASET_CSV", "../bnsl/datasets/data/NHANES_age_prediction.csv"
        ),
    )
    parser.add_argument("--workload", type=Path)
    args = parser.parse_args()
    raw, encoded = load_data(args.input)
    queries = load_queries("nhanes", raw, encoded, path=args.workload)
    model = fit_model(encoded, args.matrix)
    inference = VariableElimination(model)
    results = []
    for sql, filters in queries:
        try:
            cardinality = estimate_probability(inference, filters) * len(encoded)
        except Exception as exc:
            raise RuntimeError(
                f"Inference failed for graph {args.graph_index}, query {filters!r}"
            ) from exc
        results.append({"query_sql": sql, "estimated_cardinality": cardinality})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"graph_{args.graph_index}_cardinality.csv"
    pd.DataFrame(results).to_csv(output, index=False)
    draw_graph(model, args.output_dir, args.graph_index)
    print(f"Results saved to: {output}")


if __name__ == "__main__":
    main()
