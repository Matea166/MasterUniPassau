import pandas as pd
import numpy as np
import os
import graphviz
import sys
import ast
import warnings
import networkx as nx  # Added for cycle detection
from pgmpy.models import DiscreteBayesianNetwork
from pgmpy.estimators import MaximumLikelihoodEstimator
from pgmpy.inference import VariableElimination

warnings.simplefilter(action='ignore', category=FutureWarning)

if len(sys.argv) < 4:
    print("Usage: python script.py '<matrix>' <output_dir> <graph_index>")
    sys.exit(1)

sa_matrix_str = sys.argv[1]
output_dir = sys.argv[2]
graph_index = sys.argv[3]
sa_matrix = ast.literal_eval(sa_matrix_str)
os.makedirs(output_dir, exist_ok=True)

# ==========================================
# 1. LOAD AND PREPARE DATASET
# ==========================================
# Check if file exists to prevent silent crash

dataset_path = "../bnsl/datasets/data/movie_link.csv"

try:
    df_raw = pd.read_csv(dataset_path)
except Exception as e:
    print(f"CRITICAL ERROR: Could not read dataset {dataset_path}: {e}")
    sys.exit(1)

columns = ['movie_id', 'link_type_id', 'linked_movie_id']
MAX_STATES = 50
df_bn = df_raw[columns].copy()

for col in columns:
    df_bn[col] = df_bn[col].astype(str)
    top_items = df_bn[col].value_counts().nlargest(MAX_STATES).index
    df_bn[col] = df_bn[col].where(df_bn[col].isin(top_items), 'Other')
    df_bn[col] = df_bn[col].astype('category')

total_rows = len(df_raw)
num_vars = len(columns)

# ==========================================
# 2. STRUCTURE DEFINITION & CYCLE BREAKER
# ==========================================
adj_matrix = np.array(sa_matrix)
edges = []
for i in range(num_vars):
    for j in range(num_vars):
        if adj_matrix[i, j] == 1:
            edges.append((columns[i], columns[j]))

# Use NetworkX to find and break cycles
G = nx.DiGraph(edges)
while not nx.is_directed_acyclic_graph(G):
    cycle = nx.find_cycle(G, orientation="original")
    print(f"[Warning] Cycle detected in Graph {graph_index}: {cycle}. Removing edge {cycle[-1][:2]} to fix.")
    G.remove_edge(*cycle[-1][:2])

final_edges = list(G.edges())

# ==========================================
# 3. BUILD AND TRAIN THE BAYESIAN NETWORK
# ==========================================
bn = DiscreteBayesianNetwork(final_edges)
bn.add_nodes_from(columns)
bn.fit(df_bn, estimator=MaximumLikelihoodEstimator)
inference = VariableElimination(bn)

# ==========================================
# 4. VISUALIZE THE (FIXED) DAG
# ==========================================
try:
    dot_source = "digraph G {\n  rankdir=TB;\n  node [shape=ellipse, style=filled, fillcolor=lightblue];\n"
    for col in columns:
        dot_source += f'  "{col}";\n'
    for u, v in bn.edges():
        dot_source += f'  "{u}" -> "{v}";\n'
    dot_source += "}"

    graph_filename = os.path.join(output_dir, f"Graph_{graph_index}")
    graphviz.Source(dot_source).render(filename=graph_filename, format="png", cleanup=True)
except Exception as e:
    print(f"[Graph] Visualization Failed: {e}")


# ==========================================
# 5. CARDINALITY ESTIMATION
# ==========================================
def estimate_cardinality(query_dict):
    bn_query = {}
    for col, val in query_dict.items():
        val_str = str(val)
        valid_states = df_bn[col].unique()
        bn_query[col] = val_str if val_str in valid_states else 'Other'

    try:
        result = inference.query(variables=list(bn_query.keys()), evidence={}, show_progress=False)
        est_prob = result.get_value(**bn_query)
    except Exception:
        est_prob = 0.0
    return est_prob * total_rows


# --- RUN QUERIES ---
queries = [
    ("Q1", {'link_type_id': 6}),
    ("Q2", {'movie_id': 132249, 'link_type_id': 6}),
    ("Q3", {'movie_id': 132249, 'linked_movie_id': 1715497, 'link_type_id': 13}),
    ("Q4", {'movie_id': 132249, 'linked_movie_id': 1715497}),
    ("Q5", {'movie_id': 132249, 'link_type_id': 5}),
    ("Q6", {'movie_id': 50, 'linked_movie_id': 257907, 'link_type_id': 6})
]

queries_sql = [
    "SELECT * FROM movie_link WHERE link_type_id = 6",
    "SELECT * FROM movie_link WHERE movie_id = 132249 AND link_type_id = 6",
    "SELECT * FROM movie_link WHERE movie_id = 132249 AND linked_movie_id = 1715497 AND link_type_id = 13",
    "SELECT * FROM movie_link WHERE movie_id = 132249 AND linked_movie_id = 1715497",
    "SELECT * FROM movie_link WHERE movie_id = 132249 AND link_type_id = 5",
    "SELECT * FROM movie_link WHERE movie_id = 50 AND linked_movie_id = 257907 AND link_type_id = 6"
]

results_data = []
for (_, q_dict), sql in zip(queries, queries_sql):
    est_card = estimate_cardinality(q_dict)
    results_data.append({"query_sql": sql, "estimated_cardinality": f"{est_card:.5f}"})

csv_filename = os.path.join(output_dir, f"graph_{graph_index}_cardinality.csv")
pd.DataFrame(results_data).to_csv(csv_filename, index=False)