import pandas as pd
import numpy as np
import os
import graphviz
from pgmpy.models import BayesianNetwork
from pgmpy.estimators import MaximumLikelihoodEstimator
from pgmpy.inference import VariableElimination

# ==========================================
# 1. LOAD AND PREPARE THE DATASET
# ==========================================
print("Loading data and recreating the exact solver bins...")
df = pd.read_csv("../../bnsl/datasets/data/NHANES_age_prediction.csv")
columns = ['age_group', 'BMXBMI', 'RIAGENDR', 'DIQ010']
df = df[columns].copy()

OUTPUT_DIR="../QUBO_images"
CSV_FILE="NHANES"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Apply the exact same binning we used before the SA solver
df['BMXBMI'] = pd.cut(df['BMXBMI'], bins=[0, 18.5, 25.0, 30.0, 150.0], labels=[0, 1, 2, 3], right=False).astype(int)
df['age_group'] = df['age_group'].astype('category').cat.codes
df['RIAGENDR'] = df['RIAGENDR'].astype('category').cat.codes
df['DIQ010'] = df['DIQ010'].astype('category').cat.codes

total_rows = len(df)
num_vars = len(columns)

# ==========================================
# 2. INGEST YOUR SA SOLVER STRUCTURE
# ==========================================
sa_matrix = [
    [0, 0, 1, 1],
    [1, 0, 1, 1],
    [0, 0, 0, 0],
    [0, 0, 0, 0]
]

adj_matrix = np.array(sa_matrix)

# Extract the edges (arrows) from the 1s in the matrix
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

# Learn the probabilities by counting rows
bn.fit(df, estimator=MaximumLikelihoodEstimator)
print("Maximum Likelihood Estimation complete. CPTs built.")

# ==========================================
# 4. VISUALIZE THE QUBO MATRIX (Graphviz)
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
# 5. PRINT THE RAW PROBABILITY TABLES
# ==========================================
print("\n--- 3.5 Mathematical Transparency: Learned CPTs ---")
print("These are the exact mathematical tables the inference engine uses to answer queries.")

for node in bn.nodes():
    print(f"\nConditional Probability Table (CPT) for {node}:")
    # Get the raw table for the node
    cpd = bn.get_cpds(node)
    print(cpd)

inference = VariableElimination(bn)
print("\nVariable Elimination inference engine ready.")

# ==========================================
# 6. CARDINALITY ESTIMATION ENGINE
# ==========================================
def estimate_cardinality(query_dict, test_name):
    # 1. Ground Truth (True Cardinality from the dataframe)
    subset = df.copy()
    for col, val in query_dict.items():
        subset = subset[subset[col] == val]
    true_card = len(subset)

    # 2. Column-wise Marginal Probabilities
    col_probs = {}
    for col, val in query_dict.items():
        try:
            marg_result = inference.query(variables=[col], evidence={}, show_progress=False)
            col_probs[col] = marg_result.get_value(**{col: val})
        except Exception:
            col_probs[col] = 0.0

    # 3. Joint Probability (Selectivity) & Estimated Cardinality
    try:
        result = inference.query(variables=list(query_dict.keys()), evidence={}, show_progress=False)
        est_prob = result.get_value(**query_dict)
    except Exception:
        est_prob = 0.0

    est_card = est_prob * total_rows
    error = abs(true_card - est_card)
    
    # 4. Print results
    print(f"\n=== [{test_name}] BN QUERY [{', '.join([f'{k}={v}' for k, v in query_dict.items()])}] ===")
    print(f"True Cardinality: {true_card} rows")
    print(f"Estimated Cardinality: {est_card:.2f} rows (Abs Error: {error:.2f})")
    
    print("\nColumn-wise BN marginal probabilities:")
    for col, p in col_probs.items():
        print(f"  {col} = {query_dict[col]} -> P = {p:.10f}")
        
    print("-" * 40)
    print(f"Joint Selectivity: {est_prob:.10f}")

# ==========================================
# 7. RUN THE BENCHMARK QUERIES
# ==========================================
print("\n--- 4. Running Cardinality Benchmark ---")

queries = [
    ("Test A: Marginalization", {'DIQ010': 1}),
    ("Test B: Direct Edge Test", {'BMXBMI': 3, 'DIQ010': 0}),
    ("Test C: V-Structure Test", {'age_group': 1, 'BMXBMI': 3, 'DIQ010': 0}),
    ("Test D: Heavy Hitter", {'age_group': 0, 'BMXBMI': 1, 'DIQ010': 1}),
    ("Test E: Needle in Haystack", {'age_group': 0, 'BMXBMI': 0, 'DIQ010': 0}),
    ("Test F: Full Dimensionality", {'age_group': 1, 'RIAGENDR': 0, 'BMXBMI': 2, 'DIQ010': 1})
]

for name, q in queries:
    estimate_cardinality(q, name)