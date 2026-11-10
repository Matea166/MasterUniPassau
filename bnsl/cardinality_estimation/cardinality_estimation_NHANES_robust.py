import pandas as pd
import os
from datetime import datetime
from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation
import graphviz
from bnsl.workloads import load_queries

# ==========================================
# 1. CONFIGURATION
# ==========================================
CSV_FILE = os.environ.get("CSV_FILE", "NHANES_age_prediction")
DATA_PATH = f"datasets/data/{CSV_FILE}.csv"
OUTPUT_DIR = "../graphs"
RESULTS_DIR = "card_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# ==========================================
# 2. LOAD DATA
# ==========================================
print(f"--- Loading Data from {DATA_PATH} ---")
df_raw = pd.read_csv(DATA_PATH)
df = df_raw.copy()
categorical_cols = ['age_group', 'RIAGENDR', 'DIQ010']
for col in categorical_cols: df[col] = df[col].astype(str)
bins = [0, 18.5, 25.0, 30.0, 150.0]
labels = [0, 1, 2, 3]
df['BMXBMI'] = pd.cut(df['BMXBMI'], bins=bins, labels=labels, right=False).astype(str)

# ==========================================
# 3. TRAIN BAYESIAN NETWORK
# ==========================================

print("\n--- Training Bayesian Network ---")
discrete_cols = ['age_group', 'RIAGENDR', 'DIQ010', 'BMXBMI']
relation_discrete = Relation(df[discrete_cols])
bn = BayesianNetwork(cl_max_rows=30000).fit(relation_discrete)
bn.update(relation_discrete)

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

queries = load_queries("nhanes", df_raw, df[discrete_cols])

results_log = []

print("\n--- Running Queries and Logging Results ---")
for sql, filters in queries:
    # Calculate True Cardinality using BN filters
    subset = df.copy()
    for col, val in filters.items():
        subset = subset[subset[col] == val]
    true_card = len(subset)

    # Calculate BN Estimate
    est_prob = bn.p(**filters)
    est_card = est_prob * len(df)

    results_log.append({
        "query_sql": sql,
        "true_cardinality": true_card,
        "bn_est_cardinality": est_card,
        "est_selectivity": est_prob
    })
# ==========================================
# 7. SAVE CSV FILE
# ==========================================
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_filename = f"result_{CSV_FILE}_{timestamp}.csv"
output_path = os.path.join(RESULTS_DIR, output_filename)

pd.DataFrame(results_log).to_csv(output_path, index=False)
print(f"Results saved to: {output_path}")
