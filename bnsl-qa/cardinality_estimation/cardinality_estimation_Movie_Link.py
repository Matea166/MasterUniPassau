import pandas as pd
import numpy as np
import os
import graphviz
import warnings
from pgmpy.models import BayesianNetwork
from pgmpy.estimators import MaximumLikelihoodEstimator
from pgmpy.inference import VariableElimination

# Hide Pandas FutureWarnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# ==========================================
# 1. LOAD AND PREPARE THE DATASET
# ==========================================
print("Loading the Movie Link dataset...")
df_raw = pd.read_csv("../../bnsl/datasets/data/movie_link.csv")

columns = ['movie_id', 'link_type_id', 'linked_movie_id']
OUTPUT_DIR="../QUBO_images"
CSV_FILE="Movie_Link"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ALIGN BN DATA WITH SA SOLVER (Long-Tail Binning)
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
# 2. INGEST YOUR SA SOLVER STRUCTURE
# ==========================================
sa_matrix = [
    [0, 0, 0],
    [0, 0, 0],
    [1, 1, 0]
]
adj_matrix = np.array(sa_matrix)

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
print("\n--- 2. Parameter Learning (Calculating CPTs) ---")
# Unified to match NHANES exactly
bn = BayesianNetwork(edges)
bn.add_nodes_from(columns)

# Unified to use MaximumLikelihoodEstimator
bn.fit(df_bn, estimator=MaximumLikelihoodEstimator)
print("Maximum Likelihood Estimation complete. CPTs built.")

# ==========================================
# 4. VISUALIZE THE QUBO DAG (Graphviz)
# ==========================================
print("\n--- 3. Generating QUBO DAG Visualization ---")
try:
    dot_source = "digraph G {\n  rankdir=TB;\n  node [shape=ellipse];\n"

    for u, v in bn.edges():
        u_clean = str(u).replace(":", "_").replace(" ", "_").replace("<", "lt").replace(">", "gt")
        v_clean = str(v).replace(":", "_").replace(" ", "_").replace("<", "lt").replace(">", "gt")
        dot_source += f'  "{u_clean}" -> "{v_clean}";\n'

    dot_source += "}"
    outfile = graphviz.Source(dot_source).render(filename=f"{CSV_FILE}_bn", directory=OUTPUT_DIR, format="png", cleanup=True)
    print(f"[Graph] Saved successfully to: {outfile}")

except Exception as e:
    print(f"[Graph] Failed: {e}")

# ==========================================
# 5. MATHEMATICAL TRANSPARENCY (Print CPTs)
# ==========================================
print("\n--- 3.5 Mathematical Transparency: Learned CPTs ---")
import shutil
import collections
original_get_terminal_size = shutil.get_terminal_size
FakeTerminal = collections.namedtuple('terminal_size', ['columns', 'lines'])
shutil.get_terminal_size = lambda fallback=(80, 24): FakeTerminal(1000, 24)

for node in bn.nodes():
    print(f"\nConditional Probability Table (CPT) for {node}:")
    cpd = bn.get_cpds(node)
    print(cpd)

shutil.get_terminal_size = original_get_terminal_size

inference = VariableElimination(bn)
print("\nVariable Elimination inference engine ready.")

# ==========================================
# 6. CARDINALITY ESTIMATION ENGINE
# ==========================================
def estimate_cardinality(query_dict, test_name):
    # 1. True Cardinality from raw data
    subset = df_raw.copy()
    for col, val in query_dict.items():
        subset = subset[subset[col] == val]
    true_card = len(subset)

    # 2. Safely translate raw query into Binned States ("Other" fallback)
    bn_query = {}
    for col, val in query_dict.items():
        val_str = str(val)
        valid_states = df_bn[col].unique()
        if val_str in valid_states:
            bn_query[col] = val_str
        else:
            bn_query[col] = 'Other'

    # 3. Marginal Inference
    col_probs = {}
    for col, val in bn_query.items():
        try:
            marg_result = inference.query(variables=[col], evidence={}, show_progress=False)
            col_probs[col] = marg_result.get_value(**{col: val})
        except Exception:
            col_probs[col] = 0.0

    # 4. Joint Inference
    try:
        result = inference.query(variables=list(bn_query.keys()), evidence={}, show_progress=False)
        est_prob = result.get_value(**bn_query)
    except Exception:
        est_prob = 0.0

    est_card = est_prob * total_rows
    error = abs(true_card - est_card)

    print(f"\n=== [{test_name}] ===")
    print(f"Raw Query: {query_dict}")
    print(f"BN Translated Query: {bn_query}")
    print(f"True Cardinality: {true_card} rows")
    print(f"Estimated Cardinality: {est_card:.2f} rows (Abs Error: {error:.2f})")
    print("Column-wise BN marginal probabilities:")
    for col, p in col_probs.items():
        print(f"  {col} = {bn_query[col]} -> P = {p:.10f}")
    print("-" * 40)
    print(f"Joint Selectivity: {est_prob:.10f}")

# ==========================================
# 7. RUN THE BENCHMARK QUERIES
# ==========================================
print("\n--- 4. Running Cardinality Benchmark ---")

queries = [
    ("Q1: Baseline Marginal", {'link_type_id': 6}),
    ("Q2: Direct Parent-Child", {'movie_id': 132249, 'link_type_id': 6}),
    ("Q3: Topological Triad", {'movie_id': 132249, 'linked_movie_id': 1715497, 'link_type_id': 13}),
    ("Q4: Confounding/Existence", {'movie_id': 132249, 'linked_movie_id': 1715497}),
    ("Q5: Low Selectivity Anomaly", {'movie_id': 132249, 'link_type_id': 5}),
    ("Q6: The Long-Tail / 'Other' Test", {'movie_id': 50, 'linked_movie_id': 257907, 'link_type_id': 6})
]

for name, q in queries:
    estimate_cardinality(q, name)