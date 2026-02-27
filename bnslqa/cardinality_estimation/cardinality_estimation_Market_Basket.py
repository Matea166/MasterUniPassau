import pandas as pd
import numpy as np
import os
import graphviz
from pgmpy.models import BayesianNetwork
from pgmpy.estimators import MaximumLikelihoodEstimator
from pgmpy.inference import VariableElimination

# ==========================================
# 1. LOAD THE MARKET BASKET DATA
# ==========================================
print("Loading the 100-row Market Basket dataset...")
df = pd.read_csv("../../bnsl/datasets/data/DataMining_MarketBasket_100.csv")
columns = ['Beer', 'Bread', 'Cola', 'Diapers', 'Eggs', 'Milk']

OUTPUT_DIR="../QUBO_images"
CSV_FILE="Market_Basket"
os.makedirs(OUTPUT_DIR, exist_ok=True)

total_rows = len(df)
num_vars = len(columns)

# ==========================================
# 2. INGEST YOUR SA SOLVER STRUCTURE
# ==========================================
# Replace this with your actual SA solver matrix
sa_matrix = [
    [0, 1, 0, 1, 1, 0],
    [0, 0, 0, 0, 0, 1],
    [0, 1, 0, 1, 0, 0],
    [0, 0, 0, 0, 0, 0],
    [0, 0, 1, 0, 0, 1],
    [0, 0, 0, 0, 0, 0]
]
adj_matrix = np.array(sa_matrix)

# Extract edges from the adjacency matrix
edges = []
for i in range(num_vars):
    for j in range(num_vars):
        if adj_matrix[i, j] == 1:
            edges.append((columns[i], columns[j]))

print("\n--- 1. QUBO Learned Structure ---")
print(f"Edges discovered by SA: {edges}")


# ==========================================
# 3. BUILD AND TRAIN THE BAYESIAN NETWORK
# ==========================================
print("\n--- 3. Parameter Learning (Calculating CPTs) ---")
bn = BayesianNetwork(edges)
bn.add_nodes_from(columns)
bn.fit(df, estimator=MaximumLikelihoodEstimator)
print("Maximum Likelihood Estimation complete. CPTs built.")


# ==========================================
# 4. VISUALIZE THE QUBO DAG
# ==========================================
print("\n--- 2. Generating QUBO DAG Visualization ---")
try:
    dot_source = "digraph G {\n  rankdir=TB;\n  node [shape=ellipse];\n"

    for u, v in bn.edges():
        u_clean = str(u).replace(":", "_").replace(" ", "_").replace("<", "lt").replace(">", "gt")
        v_clean = str(v).replace(":", "_").replace(" ", "_").replace("<", "lt").replace(">", "gt")
        dot_source += f'  "{u_clean}" -> "{v_clean}";\n'

    dot_source += "}"
    outfile = graphviz.Source(dot_source).render(filename=f"{CSV_FILE}_bn", directory=OUTPUT_DIR, format="png",
                                                 cleanup=True)
    print(f"[Graph] Saved successfully to: {outfile}")

except Exception as e:
    print(f"[Graph] Failed: {e}")


# ==========================================
# 5.  PRINT THE RAW PROBABILITY TABLES
# ==========================================
print("\n--- 3.5 Mathematical Transparency: Learned CPTs ---")
for node in bn.nodes():
    print(f"\nConditional Probability Table (CPT) for {node}:")
    cpd = bn.get_cpds(node)
    print(cpd)

# Initialize inference engine
inference = VariableElimination(bn)
print("\nVariable Elimination inference engine ready.")

# ==========================================
# 5. CARDINALITY ESTIMATION ENGINE
# ==========================================
def estimate_cardinality(query_dict, test_name):
    subset = df.copy()
    for col, val in query_dict.items():
        subset = subset[subset[col] == val]
    true_card = len(subset)

    col_probs = {}
    for col, val in query_dict.items():
        try:
            marg_result = inference.query(variables=[col], evidence={}, show_progress=False)
            col_probs[col] = marg_result.get_value(**{col: val})
        except Exception:
            col_probs[col] = 0.0

    try:
        result = inference.query(variables=list(query_dict.keys()), evidence={}, show_progress=False)
        est_prob = result.get_value(**query_dict)
    except Exception:
        est_prob = 0.0

    est_card = est_prob * total_rows
    error = abs(true_card - est_card)

    print(f"\n=== [{test_name}] BN QUERY {query_dict} ===")
    print(f"True Cardinality: {true_card} rows")
    print(f"Estimated Cardinality: {est_card:.2f} rows (Abs Error: {error:.2f})")
    print("\nColumn-wise BN marginal probabilities:")
    for col, p in col_probs.items():
        print(f"  {col} = {query_dict[col]} -> P = {p:.10f}")
    print("-" * 40)
    print(f"Joint Selectivity: {est_prob:.10f}")

# ==========================================
# 6. RUN THE BENCHMARK QUERIES
# ==========================================
print("\n--- 4. Running Cardinality Benchmark ---")

queries = [
    ("Test A: ", {'Bread': 1}), 
    ("Test B: ", {'Beer': 1, 'Diapers': 1}), 
    ("Test C: ", {'Milk': 1, 'Diapers': 1}), 
    ("Test D: ", {'Eggs': 1, 'Cola': 1}), 
    ("Test E: ", {'Bread': 1, 'Diapers': 1, 'Milk': 1}), 
    ("Test F: ", {'Beer': 1, 'Bread': 0, 'Cola': 1, 'Diapers': 1, 'Eggs': 0, 'Milk': 1})
]

for name, q in queries:
    estimate_cardinality(q, name)