import argparse
import ast
import os
import sys
import warnings
from pathlib import Path

import graphviz
import networkx as nx
import numpy as np
import pandas as pd
from pgmpy.estimators import MaximumLikelihoodEstimator
from pgmpy.inference import VariableElimination
from pgmpy.models import DiscreteBayesianNetwork

from bnsl.workloads import load_queries


def estimate_cardinality(query_dict, inference, total_rows, graph_index):
    try:
        result = inference.query(
            variables=list(query_dict.keys()), evidence={}, show_progress=False
        )
        est_prob = result.get_value(**query_dict)
    except Exception as exc:
        raise RuntimeError(
            f"Inference failed for graph {graph_index}, query {query_dict!r}"
        ) from exc
    return est_prob * total_rows


def main():
    warnings.simplefilter(action="ignore", category=FutureWarning)
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=ast.literal_eval)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("graph_index")
    args = parser.parse_args()
    sa_matrix = args.matrix
    output_dir = args.output_dir
    graph_index = args.graph_index
    os.makedirs(output_dir, exist_ok=True)
    dataset_path = os.environ.get(
        "CE_DATASET_CSV", "../bnsl/datasets/data/NHANES_age_prediction.csv"
    )
    try:
        df_raw = pd.read_csv(dataset_path)
    except Exception as e:
        print(f"CRITICAL ERROR: Could not read dataset {dataset_path}: {e}")
        sys.exit(1)
    columns = ["age_group", "BMXBMI", "RIAGENDR", "DIQ010"]
    df_bn = df_raw[columns].copy()
    df_bn["BMXBMI"] = pd.cut(
        df_bn["BMXBMI"],
        bins=[0, 18.5, 25.0, 30.0, 150.0],
        labels=[0, 1, 2, 3],
        right=False,
    ).astype(int)
    df_bn["age_group"] = df_bn["age_group"].astype("category").cat.codes
    df_bn["RIAGENDR"] = df_bn["RIAGENDR"].astype("category").cat.codes
    df_bn["DIQ010"] = df_bn["DIQ010"].astype("category").cat.codes
    total_rows = len(df_bn)
    num_vars = len(columns)
    adj_matrix = np.array(sa_matrix)
    edges = []
    for i in range(num_vars):
        for j in range(num_vars):
            if adj_matrix[i, j] == 1:
                edges.append((columns[i], columns[j]))
    graph = nx.DiGraph(edges)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("Cannot estimate a cyclic graph.")
    final_edges = list(graph.edges())
    try:
        qubo_dot = graphviz.Digraph(comment="Learned Bayesian Network")
        qubo_dot.attr(rankdir="TB")
        for var in columns:
            qubo_dot.node(
                var, var, shape="ellipse", style="filled", fillcolor="lightblue"
            )
        for parent, child in final_edges:
            qubo_dot.edge(parent, child)
        graph_filename = os.path.join(output_dir, f"Graph_{graph_index}")
        qubo_dot.render(graph_filename, format="png", cleanup=True)
    except Exception as e:
        print(f"[Warning] Could not generate graph: {e}")
    bn = DiscreteBayesianNetwork(final_edges)
    bn.add_nodes_from(columns)
    bn.fit(df_bn, estimator=MaximumLikelihoodEstimator)
    inference = VariableElimination(bn)
    queries = load_queries("nhanes", df_raw, df_bn)
    results_data = []
    for sql, q_dict in queries:
        est_card = estimate_cardinality(q_dict, inference, total_rows, graph_index)
        results_data.append({"query_sql": sql, "estimated_cardinality": est_card})
    csv_filename = os.path.join(output_dir, f"graph_{graph_index}_cardinality.csv")
    pd.DataFrame(results_data).to_csv(csv_filename, index=False)
    print(
        f"Successfully generated {csv_filename} with format: query_sql,estimated_cardinality"
    )


if __name__ == "__main__":
    main()
