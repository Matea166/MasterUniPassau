import pandas as pd
import numpy as np
import os
import graphviz
import sys
import ast
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
# 1. LOAD THE DATASET
# ==========================================
print(f"Loading dataset for Graph {graph_index}...")
# Note: Ensure the CSV filename matches your local file
df = pd.read_csv("../bnsl/datasets/data/WetGrass_variance_zero.csv")

df.columns = ['cloud', 'sprinkler', 'rain', 'wetgrass']
for col in df.columns:
    df[col] = df[col].astype('category')

total_rows = len(df)
columns = df.columns.tolist()
num_vars = len(columns)

# ==========================================
# 2. STRUCTURE DEFINITION (Adjacency Matrix)
# ==========================================
adj_matrix = np.array(sa_matrix)

edges = []
for i in range(num_vars):
    for j in range(num_vars):
        if adj_matrix[i, j] == 1:
            edges.append((columns[i], columns[j]))

# ==========================================
# 3. GENERATE DAG VISUALIZATION
# ==========================================
    try:
        dot_source = "digraph G {\n  rankdir=TB;\n  node [shape=ellipse];\n"

        for i in range(num_vars):
            for j in range(num_vars):
                if adj_matrix[i, j] == 1:
                    # Clean the column names using your string replacement logic
                    u_clean = str(columns[i]).replace(":", "_").replace(" ", "_").replace("<", "lt").replace(">", "gt")
                    v_clean = str(columns[j]).replace(":", "_").replace(" ", "_").replace("<", "lt").replace(">", "gt")
                    dot_source += f'  "{u_clean}" -> "{v_clean}";\n'

        dot_source += "}"

        outfile = graphviz.Source(dot_source).render(
            filename=f"Graph_{graph_index}",
            directory=output_dir,
            format="png",
            cleanup=True
        )
        print(f"[Graph] Saved successfully to: {outfile}")

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
# 5. CARDINALITY ESTIMATION FUNCTION
# ==========================================
def estimate_cardinality(query_dict):
    try:
        result = inference.query(variables=list(query_dict.keys()), evidence={}, show_progress=False)
        est_prob = result.get_value(**query_dict)
    except Exception:
        est_prob = 0.0

    return est_prob * total_rows

# ==========================================
# 6. BENCHMARK QUERIES & CSV EXPORT
# ==========================================
queries = [
    ("Test A", {'wetgrass': 'f'}),
    ("Test B", {'rain': 'f', 'wetgrass': 'f'}),
    ("Test C", {'sprinkler': 'off', 'rain': 'f', 'wetgrass': 'f'}),
    ("Test D", {'cloud': 'f', 'sprinkler': 'off', 'rain': 'f'}),
    ("Test E", {'cloud': 't', 'sprinkler': 'on', 'rain': 'f'}),
    ("Test F", {'cloud': 't', 'sprinkler': 'off', 'rain': 't', 'wetgrass': 'f'})
]

queries_sql = [
    "SELECT * FROM wetgrass_data WHERE wetgrass = 'f'",
    "SELECT * FROM wetgrass_data WHERE rain = 'f' AND wetgrass = 'f'",
    "SELECT * FROM wetgrass_data WHERE sprinkler = 'off' AND rain = 'f' AND wetgrass = 'f'",
    "SELECT * FROM wetgrass_data WHERE cloud = 'f' AND sprinkler = 'off' AND rain = 'f'",
    "SELECT * FROM wetgrass_data WHERE cloud = 't' AND sprinkler = 'on' AND rain = 'f'",
    "SELECT * FROM wetgrass_data WHERE cloud = 't' AND sprinkler = 'off' AND rain = 't' AND wetgrass = 'f'"
]

results_data = []
for (_, q_dict), sql in zip(queries, queries_sql):
    est_card = estimate_cardinality(q_dict)
    results_data.append({"query_sql": sql, "estimated_cardinality": f"{est_card:.5f}"})

# Save intermediate CSV

csv_filename = os.path.join(output_dir, f"graph_{graph_index}_cardinality.csv")
pd.DataFrame(results_data).to_csv(csv_filename, index=False)


# ==========================================
# 6. BENCHMARK QUERIES & CSV EXPORT
# ==========================================
queries = [
    ("Test A", {'wetgrass': 'f'}),
    ("Test B", {'rain': 'f', 'wetgrass': 'f'}),
    ("Test C", {'sprinkler': 'off', 'rain': 'f', 'wetgrass': 'f'}),
    ("Test D", {'cloud': 'f', 'sprinkler': 'off', 'rain': 'f'}),
    ("Test E", {'cloud': 't', 'sprinkler': 'on', 'rain': 'f'}),
    ("Test F", {'cloud': 't', 'sprinkler': 'off', 'rain': 't', 'wetgrass': 'f'})
]

queries_sql = [
    "SELECT * FROM wetgrass_data WHERE wetgrass = 'f'",
    "SELECT * FROM wetgrass_data WHERE rain = 'f' AND wetgrass = 'f'",
    "SELECT * FROM wetgrass_data WHERE sprinkler = 'off' AND rain = 'f' AND wetgrass = 'f'",
    "SELECT * FROM wetgrass_data WHERE cloud = 'f' AND sprinkler = 'off' AND rain = 'f'",
    "SELECT * FROM wetgrass_data WHERE cloud = 't' AND sprinkler = 'on' AND rain = 'f'",
    "SELECT * FROM wetgrass_data WHERE cloud = 't' AND sprinkler = 'off' AND rain = 't' AND wetgrass = 'f'"
]

results_data = []
for (_, q_dict), sql in zip(queries, queries_sql):
    est_card = estimate_cardinality(q_dict)
    results_data.append({"query_sql": sql, "estimated_cardinality": f"{est_card:.5f}"})

# Save intermediate CSV

csv_filename = os.path.join(output_dir, f"graph_{graph_index}_cardinality.csv")
pd.DataFrame(results_data).to_csv(csv_filename, index=False)
