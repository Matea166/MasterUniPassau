from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation
import pandas as pd
import os
import graphviz

# ==========================================
# 1. CONFIGURATION
# ==========================================
CSV_FILE = "NHANES_age_prediction"
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
# Keep age_group, RIAGENDR, DIQ010 as-is but as strings
categorical_cols = ['age_group', 'RIAGENDR', 'DIQ010']
for col in categorical_cols:
    df[col] = df[col].astype(str)

# ==========================================
# 2b. APPLY WHO MEDICAL BINS FOR BMI
# ==========================================
# Exactly like your original code
bins = [0, 18.5, 25.0, 30.0, 150.0]
labels = [0, 1, 2, 3]
df['BMXBMI'] = pd.cut(df['BMXBMI'], bins=bins, labels=labels, right=False).astype(str)

print(f"Total rows in bucketed dataset: {len(df)}")

# ==========================================
# 3. TRAIN BAYESIAN NETWORK (DISCRETE STRUCTURE)
# ==========================================
print("\n--- Training Bayesian Network ---")

# Select only discrete columns for structure learning
discrete_cols = ['age_group', 'RIAGENDR', 'DIQ010', 'BMXBMI']
relation_discrete = Relation(df[discrete_cols])

# Fit structure on discrete data only
bn = BayesianNetwork(cl_max_rows=30000).fit(relation_discrete)

# Update BN with full dataset to get accurate histograms
relation_full = Relation(df)  # includes continuous columns too
bn.update(relation_full)

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
    # --------------------------
    # True cardinality (Ground Truth)
    # --------------------------
    subset = df.copy()
    for col, val in filters.items():
        subset = subset[subset[col] == val]
    true_card = len(subset)

    # --------------------------
    # Column-wise independent probabilities
    # --------------------------
    col_probs = {}
    for col, val in filters.items():
        p = bn.p(**{col: val})
        col_probs[col] = p

    # --------------------------
    # Joint probability (Selectivity) & Cardinality
    # --------------------------
    est_prob = bn.p(**filters)
    est_card = est_prob * len(df)

    # --------------------------
    # Print results
    # --------------------------
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
print_bn_estimate(bn, df, {'DIQ010': '2.0'})
print_bn_estimate(bn, df, {'BMXBMI': '3', 'DIQ010': '1.0'})
print_bn_estimate(bn, df, {'age_group': 'Senior', 'BMXBMI': '3', 'DIQ010': '1.0'})
print_bn_estimate(bn, df, {'age_group': 'Adult', 'BMXBMI': '1', 'DIQ010': '2.0'})
print_bn_estimate(bn, df, {'age_group': 'Adult', 'BMXBMI': '0', 'DIQ010': '1.0'})
print_bn_estimate(bn, df, {'age_group': 'Senior', 'RIAGENDR': '1.0', 'BMXBMI': '2', 'DIQ010': '2.0'})
print("\nProcessing Complete.")