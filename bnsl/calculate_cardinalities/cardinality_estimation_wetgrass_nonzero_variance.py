from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation
import pandas as pd
import os
import graphviz

# ==========================================
# 1. CONFIGURATION
# ==========================================
CSV_FILE = "WetGrass_variance_non_zero"
DATA_PATH = f"../datasets/data/{CSV_FILE}.csv"
OUTPUT_DIR = "../graphs"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# 2. LOAD DATA
# ==========================================
print(f"--- Loading Data from {DATA_PATH} ---")
df = pd.read_csv(DATA_PATH)

# ==========================================
# 2a. PREPROCESSING CATEGORICAL DATA
# ==========================================
# All columns are binary/categorical, ensure they are strings
for col in df.columns:
    df[col] = df[col].astype(str)

print(f"Total rows in dataset: {len(df)}")

# ==========================================
# 3. TRAIN BAYESIAN NETWORK (DISCRETE STRUCTURE)
# ==========================================
print("\n--- Training Bayesian Network ---")

relation = Relation(df)
bn = BayesianNetwork(cl_max_rows=30000).fit(relation)
bn.update(relation)  # no continuous variables, just reinforce counts

print("Bayesian Network training complete.")

# ==========================================
# 4. GENERATE GRAPH
# ==========================================
print("\n--- Generating Graph ---")
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
# 5. PURE BN ESTIMATION ENGINE
# ==========================================
def print_bn_estimate(bn, df, filters):

   # Strict Pure BN Estimator for Database Queries

    # True cardinality
    subset = df.copy()
    for col, val in filters.items():
        subset = subset[subset[col] == val]
    true_card = len(subset)

    # Column-wise independent probabilities
    col_probs = {}
    for col, val in filters.items():
        col_probs[col] = bn.p(**{col: val})

    # Joint probability & estimated cardinality
    est_prob = bn.p(**filters)
    est_card = est_prob * len(df)

    # Print results
    print(f"\n=== BN QUERY [{', '.join([f'{k}={v}' for k, v in filters.items()])}] ===")
    print(f"True Cardinality: {true_card} rows")
    print(f"Estimated Cardinality: {est_card:.2f} rows\n")

    print("Column-wise BN probabilities:")
    for col, p in col_probs.items():
        print(f"  {col} = {filters[col]} -> P = {p:.10f}")

    print("-" * 40)
    print(f"Joint Selectivity: {est_prob:.10f}")

# ==========================================
# 6. EXECUTING BENCHMARK QUERIES
# ==========================================
print("\n--- Executing Queries ---")
print_bn_estimate(bn, df, {'WetGrass': 'f'})
print_bn_estimate(bn, df, {'Rain': 'f', 'WetGrass': 'f'})
print_bn_estimate(bn, df, {'Sprinkler': 'off', 'Rain': 'f', 'WetGrass': 'f'})
print_bn_estimate(bn, df, {'Cloud': 'f', 'Sprinkler': 'off', 'Rain': 'f'})
print_bn_estimate(bn, df, {'Cloud': 't', 'Sprinkler': 'on', 'Rain': 'f'})
print_bn_estimate(bn, df, {'Cloud': 't', 'Sprinkler': 'off', 'Rain': 't', 'WetGrass': 'f'})
print("\nProcessing Complete.")