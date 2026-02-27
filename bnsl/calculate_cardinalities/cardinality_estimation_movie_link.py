from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation
import pandas as pd
import os
import graphviz

# ==========================================
# 1. CONFIGURATION
# ==========================================
CSV_FILE = "movie_link"
DATA_PATH = f"bn/data/{CSV_FILE}.csv"
OUTPUT_DIR = "../output_bn"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# 2. LOAD DATA
# ==========================================
print(f"--- Loading Data from {DATA_PATH} ---")
df = pd.read_csv(DATA_PATH)

# Drop 'id' column since we don't want it
if 'id' in df.columns:
    df = df.drop(columns=['id'])

print(f"Columns used for BN: {df.columns.tolist()}")
print(f"Total rows: {len(df)}")

# ==========================================
# 3. TRAIN BAYESIAN NETWORK (DISCRETE STRUCTURE)
# ==========================================
print("\n--- Training Bayesian Network ---")

# All columns are discrete already
relation_discrete = Relation(df)

# Fit BN on discrete data
bn = BayesianNetwork(cl_max_rows=30000).fit(relation_discrete)

# Update BN with full data to get accurate probabilities
bn.update(relation_discrete)

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
    """
    Strict Pure BN Estimator for Database Queries
    """
    # True cardinality
    subset = df.copy()
    for col, val in filters.items():
        subset = subset[subset[col] == val]
    true_card = len(subset)

    # Column-wise probabilities
    col_probs = {col: bn.p(**{col: val}) for col, val in filters.items()}

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
# Example queries for your movie_links data
print_bn_estimate(bn, df, {'link_type_id': 6})
print_bn_estimate(bn, df, {'movie_id': 50, 'link_type_id': 6})
print_bn_estimate(bn, df, {'movie_id': 50, 'linked_movie_id': 257907, 'link_type_id': 6})
print_bn_estimate(bn, df, {'linked_movie_id': 257907})
print_bn_estimate(bn, df, {'movie_id': 164083, 'linked_movie_id': 164081, 'link_type_id': 2})

print("\nProcessing Complete.")