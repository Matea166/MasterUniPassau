import pandas as pd
import os
from datetime import datetime
from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation
import graphviz

# ==========================================
# 1. CONFIGURATION
# ==========================================
CSV_FILE = "DataMining_MarketBasket_10K"  # Base name without .csv extension
DATA_PATH = f"bn/data/{CSV_FILE}.csv"
OUTPUT_DIR = "../output_bn"
RESULTS_DIR = "card_results"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# ==========================================
# 2. LOAD DATA
# ==========================================
print(f"--- Loading Data from {DATA_PATH} ---")
df = pd.read_csv(DATA_PATH)

# Ensure all data is treated as strings (categorical/binary)
for col in df.columns:
    df[col] = df[col].astype(str)

print(f"Total rows in dataset: {len(df)}")
print(f"Columns: {df.columns.tolist()}")

# ==========================================
# 3. TRAIN BAYESIAN NETWORK
# ==========================================
print("\n--- Training Bayesian Network ---")
relation = Relation(df)
bn = BayesianNetwork(cl_max_rows=30000).fit(relation)
bn.update(relation)
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
# 5. CSV EXPORT & ESTIMATION LOGIC
# ==========================================
def parse_sql_to_filter(sql, df_columns):
    """
    Parses SQL and matches columns to the DataFrame headers case-insensitively.
    """
    where_clause = sql.split("WHERE")[-1].strip()
    conditions = [c.strip() for c in where_clause.split("AND")]
    filters = {}

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


# SQL-style queries for the Market Basket data
queries_sql = [
    "SELECT * FROM transactions WHERE Bread = '1'",
    "SELECT * FROM transactions WHERE Beer = '1' AND Diapers = '1'",
    "SELECT * FROM transactions WHERE Milk = '1' AND Diapers = '1'",
    "SELECT * FROM transactions WHERE Eggs = '1' AND Cola = '1'",
    "SELECT * FROM transactions WHERE Bread = '1' AND Diapers = '1' AND Milk = '1'",
    "SELECT * FROM transactions WHERE Beer = '1' AND Bread = '0' AND Cola = '1' AND Diapers = '1' AND Eggs = '0' AND Milk = '1'"
]

results_log = []

print("\n--- Running Queries and Logging Results ---")
for sql in queries_sql:
    filters = parse_sql_to_filter(sql, df.columns)

    # 1. Calculate True Cardinality
    subset = df.copy()
    for col, val in filters.items():
        subset = subset[subset[col] == val]
    true_card = len(subset)

    # 2. Calculate BN Estimate
    est_prob = bn.p(**filters)
    est_card = est_prob * len(df)

    # 3. Append to list for CSV export
    results_log.append({
        "query_sql": sql,
        "true_cardinality": true_card,
        "bn_est_cardinality": round(est_card, 2),
        "est_selectivity": f"{est_prob:.10f}"
    })

    print(f"Query: {sql}")
    print(f" -> True: {true_card} | Est: {est_card:.2f} (Prob: {est_prob:.6f})")

# ==========================================
# 6. SAVE CSV FILE
# ==========================================
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_filename = f"result_{CSV_FILE}_{timestamp}.csv"
output_path = os.path.join(RESULTS_DIR, output_filename)

results_df = pd.DataFrame(results_log)
results_df.to_csv(output_path, index=False)

print(f"\nProcessing Complete. Results saved to: {output_path}")