import pandas as pd
import numpy as np
import os
import graphviz
import sys
import ast
from bnsl.workloads import load_queries
from pgmpy.models import DiscreteBayesianNetwork
from pgmpy.estimators import MaximumLikelihoodEstimator
from pgmpy.inference import VariableElimination

# --- ARGUMENT PARSING FROM SHELL ---
if len(sys.argv) < 4:
    print("Usage: python script.py '<matrix>' <output_dir> <graph_index>")
    sys.exit(1)

sa_matrix_str = sys.argv[1]
output_dir = sys.argv[2]
graph_index = sys.argv[3]

# Convert matrix string into a Python list
sa_matrix = ast.literal_eval(sa_matrix_str)
os.makedirs(output_dir, exist_ok=True)

# ==========================================
# 1. LOAD THE MARKET BASKET DATA
# ==========================================
print(f"Loading Market Basket dataset for Graph {graph_index}...")
df = pd.read_csv(os.environ.get("CE_DATASET_CSV", "../bnsl/datasets/data/DataMining_MarketBasket_100.csv"))

columns = ['Beer', 'Bread', 'Cola', 'Diapers', 'Eggs', 'Milk']
total_rows = len(df)
num_vars = len(columns)

# Convert columns to category type (required by pgmpy)
for col in columns:
    if col in df.columns:
        df[col] = df[col].astype('category')

# ==========================================
# 2. STRUCTURE DEFINITION (Adjacency Matrix)
# ==========================================
adj_matrix = np.array(sa_matrix)

# Extract edges from the adjacency matrix
edges = []
for i in range(num_vars):
    for j in range(num_vars):
        if adj_matrix[i, j] == 1:
            edges.append((columns[i], columns[j]))

# ==========================================
# 3. VISUALIZE THE QUBO DAG
# ==========================================

try:
    qubo_dot = graphviz.Digraph(comment='Market Basket Bayesian Network')
    qubo_dot.attr(rankdir='TB')

    for var in columns:
        qubo_dot.node(var, var, shape='ellipse', style='filled', fillcolor='lightblue')

    for i in range(num_vars):
        for j in range(num_vars):
            if adj_matrix[i, j] == 1:
                qubo_dot.edge(columns[i], columns[j])

    graph_filename = os.path.join(output_dir, f"Graph_{graph_index}")
    qubo_dot.render(graph_filename, format='png', cleanup=True)
except Exception as e:
    print(f"[Warning] Could not generate graph: {e}")

# ==========================================
# 4. BUILD AND TRAIN THE BAYESIAN NETWORK
# ==========================================
bn = DiscreteBayesianNetwork(edges)
bn.add_nodes_from(columns)
bn.fit(df, estimator=MaximumLikelihoodEstimator)
inference = VariableElimination(bn)

# ==========================================
# 5. CARDINALITY ESTIMATION ENGINE
# ==========================================
def estimate_cardinality(query_dict):
    try:
        result = inference.query(variables=list(query_dict.keys()), evidence={}, show_progress=False)
        est_prob = result.get_value(**query_dict)
    except Exception as exc:
        raise RuntimeError(
            f"Inference failed for graph {graph_index}, query {query_dict!r}"
        ) from exc

    return est_prob * total_rows

# ==========================================
# 6. BENCHMARK QUERIES & CSV EXPORT
# ==========================================
queries = load_queries("market_basket", df, df)

results_data = []

for sql, q_dict in queries:
    est_card = estimate_cardinality(q_dict)
    results_data.append({"query_sql": sql, "estimated_cardinality": f"{est_card:.5f}"})

# Save intermediate CSV
csv_filename = os.path.join(output_dir, f"graph_{graph_index}_cardinality.csv")
pd.DataFrame(results_data).to_csv(csv_filename, index=False)
