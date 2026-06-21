import pandas as pd
import os
from datetime import datetime
from phd.bn import BayesianNetwork
from phd.rel import Relation
import graphviz

# ==========================================
# 1. CONFIGURATION
# ==========================================
CSV_FILE = "WetGrass_variance_zero"  # Base name without .csv extension
DATA_PATH = f"bn/data/{CSV_FILE}.csv"
OUTPUT_DIR = "../output_bn"
RESULTS_DIR = "card_results"  # New directory for CSV results

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# ==========================================
# 2. LOAD DATA
# ==========================================
df = pd.read_csv(DATA_PATH)
for col in df.columns:
    df[col] = df[col].astype(str)

# ==========================================
# 3. TRAIN BAYESIAN NETWORK
# ==========================================
relation = Relation(df)
bn = BayesianNetwork(cl_max_rows=30000).fit(relation)
bn.update(relation)

# ==========================================
# 4. CSV EXPORT LOGIC
# ==========================================
def parse_sql_to_filter(sql, df_columns):
    """
    Parses SQL and matches columns to the DataFrame headers case-insensitively.
    """
    where_clause = sql.split("WHERE")[-1].strip()
    conditions = [c.strip() for c in where_clause.split("AND")]
    filters = {}
    
    # Create a map of lowercase names to actual CSV column names
    col_map = {c.lower(): c for c in df_columns}
    
    for cond in conditions:
        parts = cond.replace("'", "").split("=")
        sql_col = parts[0].strip().lower()
        val = parts[1].strip()
        
        if sql_col in col_map:
            filters[col_map[sql_col]] = val
        else:
            print(f"Warning: Column '{sql_col}' not found in dataset.")
            
    return filters

queries_sql = [
    "SELECT * FROM wetgrass_data WHERE wetgrass = 'f'",
    "SELECT * FROM wetgrass_data WHERE cloud = 't' AND wetgrass = 't'",
    "SELECT * FROM wetgrass_data WHERE rain = 't' AND wetgrass = 't'",
    "SELECT * FROM wetgrass_data WHERE sprinkler = 'on' AND rain = 'f'",
    "SELECT * FROM wetgrass_data WHERE cloud = 't' AND sprinkler = 'on' AND rain = 'f'",
    "SELECT * FROM wetgrass_data WHERE cloud = 't' AND sprinkler = 'off' AND rain = 'f' AND wetgrass = 'f'"
]

results_log = []

print("\n--- Running Queries and Logging Results ---")
for sql in queries_sql:
    # Pass df.columns to ensure we find the right keys
    filters = parse_sql_to_filter(sql, df.columns)
    
    # 1. Calculate True Cardinality
    subset = df.copy()
    for col, val in filters.items():
        subset = subset[subset[col] == val]
    true_card = len(subset)

    # 2. Calculate BN Estimate
    # Use **filters to pass the dictionary as arguments
    est_prob = bn.p(**filters)
    est_card = est_prob * len(df)

    # 3. Append to list for CSV
    results_log.append({
        "query_sql": sql,
        "true_cardinality": true_card,
        "est_cardinality": round(est_card, 2),
        "est_selectivity": f"{est_prob:.10f}"
    })

# ==========================================
# 5. SAVE CSV FILE
# ==========================================
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_filename = f"result_{CSV_FILE}_{timestamp}.csv"
output_path = os.path.join(RESULTS_DIR, output_filename)

results_df = pd.DataFrame(results_log)
results_df.to_csv(output_path, index=False)

print(f"Results saved to: {output_path}")
