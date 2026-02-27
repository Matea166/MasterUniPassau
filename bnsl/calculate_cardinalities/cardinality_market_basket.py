from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation
import pandas as pd
import os
import graphviz

# ==========================================
# 1. CONFIGURATION
# ==========================================
CSV_FILE = "DataMining_MarketBasket_100"
DATA_PATH = f"bn/data/{CSV_FILE}.csv"
OUTPUT_DIR = "../output_bn"

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
    dot_file = os.path.join(OUTPUT_DIR, f"{CSV_FILE}_bn.dot")
    png_file = os.path.join(OUTPUT_DIR, f"{CSV_FILE}_bn.png")

    with open(dot_file, "w") as f:
        f.write(str(bn.to_dot()))

    graphviz.render("dot", "png", dot_file, outfile=png_file)
    print(f"[Graph] Saved to: {png_file}")
except Exception as e:
    print(f"[Graph] Warning: {e}")

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
print_bn_estimate(bn, df, {'Bread': '1'})
print_bn_estimate(bn, df, {'Beer': '1', 'Diapers': '1'})
print_bn_estimate(bn, df, {'Milk': '1', 'Diapers': '1'})
print_bn_estimate(bn, df, {'Eggs': '1', 'Cola': '1'})
print_bn_estimate(bn, df, {'Bread': '1', 'Milk': '1', 'Diapers': '1'})
print_bn_estimate(bn, df, {'Beer': '1', 'Bread': '0', 'Cola': '1', 'Diapers': '1', 'Eggs': '0', 'Milk': '1'})
print("\nProcessing Complete.")