import pandas as pd
import os
from datetime import datetime
from phd.bn import BayesianNetwork
from phd.rel import Relation
import graphviz

# [Keep your CONFIGURATION, LOAD, and TRAIN sections exactly the same...]
CSV_FILE = "NHANES_age_prediction"
DATA_PATH = f"../datasets/data/{CSV_FILE}.csv"
OUTPUT_DIR = "../graphs"
RESULTS_DIR = "card_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

print(f"--- Loading Data from {DATA_PATH} ---")
df_raw = pd.read_csv(DATA_PATH)
df = df_raw.copy()
categorical_cols = ['age_group', 'RIAGENDR', 'DIQ010']
for col in categorical_cols: df[col] = df[col].astype(str)
bins = [0, 18.5, 25.0, 30.0, 150.0]
labels = [0, 1, 2, 3]
df['BMXBMI'] = pd.cut(df['BMXBMI'], bins=bins, labels=labels, right=False).astype(str)

print("\n--- Training Bayesian Network ---")
discrete_cols = ['age_group', 'RIAGENDR', 'DIQ010', 'BMXBMI']
relation_discrete = Relation(df[discrete_cols])
bn = BayesianNetwork(cl_max_rows=30000).fit(relation_discrete)
bn.update(Relation(df))

# ==========================================
# 4. TRIPLE QUERY MAPPING
# ==========================================
# A. Exactly matches the SA/SQA file (Used for joining the final CSVs)
sa_queries = [
    "SELECT * FROM nhanes_data WHERE DIQ010 = 1",
    "SELECT * FROM nhanes_data WHERE BMXBMI = 3 AND DIQ010 = 0",
    "SELECT * FROM nhanes_data WHERE age_group = 1 AND BMXBMI = 3 AND DIQ010 = 0",
    "SELECT * FROM nhanes_data WHERE age_group = 0 AND BMXBMI = 1 AND DIQ010 = 1",
    "SELECT * FROM nhanes_data WHERE age_group = 0 AND BMXBMI = 2 AND DIQ010 = 0",
    "SELECT * FROM nhanes_data WHERE age_group = 1 AND RIAGENDR = 0 AND BMXBMI = 2 AND DIQ010 = 1"
]

# B. Translates the bins to raw values for Postgres execution in the .sh script
pg_queries = [
    "SELECT * FROM nhanes_data WHERE DIQ010 = 2",
    "SELECT * FROM nhanes_data WHERE BMXBMI >= 30.0 AND DIQ010 = 1",
    "SELECT * FROM nhanes_data WHERE age_group = 'Senior' AND BMXBMI >= 30.0 AND DIQ010 = 1",
    "SELECT * FROM nhanes_data WHERE age_group = 'Adult' AND BMXBMI >= 18.5 AND BMXBMI < 25.0 AND DIQ010 = 2",
    "SELECT * FROM nhanes_data WHERE age_group = 'Adult' AND BMXBMI >= 25.0 AND BMXBMI < 30.0 AND DIQ010 = 1",
    "SELECT * FROM nhanes_data WHERE age_group = 'Senior' AND RIAGENDR = 1 AND BMXBMI >= 25.0 AND BMXBMI < 30.0 AND DIQ010 = 2"
]

# C. Translates to the string formats expected by the Bayesian Network
bn_filters = [
    {'DIQ010': '2.0'},
    {'BMXBMI': '3', 'DIQ010': '1.0'},
    {'age_group': 'Senior', 'BMXBMI': '3', 'DIQ010': '1.0'},
    {'age_group': 'Adult', 'BMXBMI': '1', 'DIQ010': '2.0'},
    {'age_group': 'Adult', 'BMXBMI': '2', 'DIQ010': '1.0'},
    {'age_group': 'Senior', 'RIAGENDR': '1.0', 'BMXBMI': '2', 'DIQ010': '2.0'}
]


# ==========================================
# 5. EXECUTION & LOGGING
# ==========================================
results_log = []

print("\n--- Running Queries and Logging Results ---")
for i in range(len(sa_queries)):
    sa_sql = sa_queries[i]
    pg_sql = pg_queries[i]
    filters = bn_filters[i]
    
    # Calculate True Cardinality using BN filters
    subset = df.copy()
    for col, val in filters.items():
        subset = subset[subset[col] == val]
    true_card = len(subset)

    # Calculate BN Estimate
    est_prob = bn.p(**filters)
    est_card = est_prob * len(df)

    # Export BOTH SA and PG queries to the CSV
    results_log.append({
        "sa_query_sql": sa_sql,
        "pg_query_sql": pg_sql,
        "true_cardinality": true_card,
        "bn_est_cardinality": round(est_card, 2),
        "est_selectivity": f"{est_prob:.10f}"
    })
# ==========================================
# 6. SAVE CSV FILE
# ==========================================
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_filename = f"result_{CSV_FILE}_{timestamp}.csv"
output_path = os.path.join(RESULTS_DIR, output_filename)

pd.DataFrame(results_log).to_csv(output_path, index=False)
print(f"Results saved to: {output_path}")
