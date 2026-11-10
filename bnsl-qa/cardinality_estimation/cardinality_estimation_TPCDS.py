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

from bnsl.datasets.tpcds_encoding import (
    COLUMNS, DATA_PATH, STATE_NAMES, WORKLOAD_PATH, assignments, encode, load_queries,
)


def fit_model(encoded, matrix):
    matrix = np.asarray(matrix)
    if matrix.shape != (8, 8) or not np.isin(matrix, [0, 1]).all():
        raise ValueError("Expected an 8 by 8 binary adjacency matrix.")
    edges = [(COLUMNS[i], COLUMNS[j]) for i, j in zip(*np.nonzero(matrix))]
    model = DiscreteBayesianNetwork()
    model.add_nodes_from(COLUMNS)
    model.add_edges_from(edges)
    if not nx.is_directed_acyclic_graph(model):
        raise ValueError("Cannot estimate a cyclic graph.")
    if any(degree > 2 for _, degree in model.in_degree()):
        raise ValueError("Expected at most two parents per variable.")
    model.fit(encoded, estimator=MaximumLikelihoodEstimator, state_names=STATE_NAMES)
    model.check_model()
    return model


def estimate_probability(inference, filters):
    if any(not states for states in filters.values()):
        return 0.0
    result = inference.query(variables=list(filters), evidence={}, show_progress=False)
    return sum(float(result.get_value(**query)) for query in assignments(filters))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=ast.literal_eval)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("graph_index")
    parser.add_argument("--input", type=Path, default=os.environ.get("CE_DATASET_CSV", DATA_PATH))
    parser.add_argument("--workload", type=Path, default=WORKLOAD_PATH)
    args = parser.parse_args()
    encoded = encode(pd.read_csv(args.input))
    queries = load_queries(args.workload)
    model = fit_model(encoded, args.matrix)
    inference = VariableElimination(model)
    results = [{"query_sql": query["sql"],
                "estimated_cardinality": estimate_probability(inference, filters) * len(encoded)}
               for query, filters in queries]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"graph_{args.graph_index}_cardinality.csv"
    pd.DataFrame(results).to_csv(output, index=False)
    graph = graphviz.Digraph()
    for column in COLUMNS:
        graph.node(column)
    graph.edges(model.edges())
    graph.render(str(args.output_dir / f"Graph_{args.graph_index}"), format="png", cleanup=True)
    print(f"Results saved to: {output}")


if __name__ == "__main__":
    main()
