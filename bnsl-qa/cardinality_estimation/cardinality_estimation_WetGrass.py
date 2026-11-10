import ast
import os
import sys

import graphviz
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
    if len(sys.argv) < 4:
        print("Usage: python script.py '<matrix>' <output_dir> <graph_index>")
        sys.exit(1)
    sa_matrix_str = sys.argv[1]
    output_dir = sys.argv[2]
    graph_index = sys.argv[3]
    sa_matrix = ast.literal_eval(sa_matrix_str)
    os.makedirs(output_dir, exist_ok=True)
    print(f"Loading dataset for Graph {graph_index}...")
    df = pd.read_csv(
        os.environ.get(
            "CE_DATASET_CSV", "../bnsl/datasets/data/WetGrass_variance_zero.csv"
        )
    )
    df.columns = ["cloud", "sprinkler", "rain", "wetgrass"]
    for col in df.columns:
        df[col] = df[col].astype("category")
    total_rows = len(df)
    columns = df.columns.tolist()
    num_vars = len(columns)
    adj_matrix = np.array(sa_matrix)
    edges = []
    for i in range(num_vars):
        for j in range(num_vars):
            if adj_matrix[i, j] == 1:
                edges.append((columns[i], columns[j]))
    try:
        qubo_dot = graphviz.Digraph(comment="Learned Bayesian Network")
        qubo_dot.attr(rankdir="TB")
        for var in columns:
            qubo_dot.node(
                var, var, shape="ellipse", style="filled", fillcolor="lightblue"
            )
        for i in range(num_vars):
            for j in range(num_vars):
                if adj_matrix[i, j] == 1:
                    qubo_dot.edge(columns[i], columns[j])
        graph_filename = os.path.join(output_dir, f"Graph_{graph_index}")
        qubo_dot.render(graph_filename, format="png", cleanup=True)
    except Exception as e:
        print(f"[Warning] Could not generate graph: {e}")
    bn = DiscreteBayesianNetwork(edges)
    bn.add_nodes_from(columns)
    bn.fit(df, estimator=MaximumLikelihoodEstimator)
    inference = VariableElimination(bn)
    queries = load_queries("wetgrass", df, df)
    results_data = []
    for sql, q_dict in queries:
        est_card = estimate_cardinality(q_dict, inference, total_rows, graph_index)
        results_data.append({"query_sql": sql, "estimated_cardinality": est_card})
    csv_filename = os.path.join(output_dir, f"graph_{graph_index}_cardinality.csv")
    pd.DataFrame(results_data).to_csv(csv_filename, index=False)


if __name__ == "__main__":
    main()
