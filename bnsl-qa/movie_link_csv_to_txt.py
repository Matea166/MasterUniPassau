import pandas as pd
import os

# ==========================================
# 1. LOAD THE DATA
# ==========================================
csv_file = "../bnsl/datasets/data/movie_link.csv"
df = pd.read_csv(csv_file)

# Drop the primary key 'id' as it is just a row number
if 'id' in df.columns:
    df = df.drop(columns=['id'])

print(f"Original Dataset: {len(df)} rows.")

# ==========================================
# 2. STABLE LONG-TAIL BINNING (The 6-State Fix)
# ==========================================
# Capped at 5 to prevent BDeu log-gamma function overflow during QUBO reads.
# This keeps the Top 5 most important hubs and merges the rest into "Other" (the 6th state).
MAX_STATES = 5


def cap_states(series, max_states):
    series = series.astype(str)
    top_items = series.value_counts().nlargest(max_states).index
    return series.where(series.isin(top_items), 'Other')


for col in df.columns:
    df[col] = cap_states(df[col], MAX_STATES)
    # Force the column to be categorized immediately
    df[col] = df[col].astype('category')

print(f"Filtered Dataset: {len(df)} rows (100% of data preserved)")

# ==========================================
# 3. EXPORT DICTIONARIES & ENCODE
# ==========================================
print("\n" + "=" * 50)
print("     TRANSLATION DICTIONARIES (SAVE THIS)")
print("=" * 50)
print("Movie IDs:\n", dict(enumerate(df['movie_id'].cat.categories)), "\n")
print("Linked Movie IDs:\n", dict(enumerate(df['linked_movie_id'].cat.categories)), "\n")
print("Link Types:\n", dict(enumerate(df['link_type_id'].cat.categories)), "\n")
print("=" * 50 + "\n")

# Convert the text categories into 0-indexed integers
for col in df.columns:
    df[col] = df[col].cat.codes

# ==========================================
# 4. PREPARE THE SA SOLVER FORMAT (.txt)
# ==========================================
num_vars = len(df.columns)
# Because of MAX_STATES=5 + 'Other', this will output 6 for each column
states_per_var = [str(df[col].nunique()) for col in df.columns]

dummy_length = num_vars * (num_vars - 1)
dummy_matrix = " ".join(["0"] * dummy_length)

os.makedirs("qa-datasets", exist_ok=True)
output_file = "qa-datasets/MovieLink_Capped_3vars.txt"

with open(output_file, 'w') as f:
    # This writes "3 6 6 6"
    f.write(f"{num_vars} {' '.join(states_per_var)}\n")
    f.write("MovieLink_Capped_3Vars\n")
    f.write(f"{dummy_matrix}\n")

    for index, row in df.iterrows():
        row_str = " ".join(row.astype(str).tolist())
        f.write(f"{row_str}\n")

print(f"Success! All {len(df)} rows saved to {output_file}.")
print(f"The solver header is exactly: {num_vars} {' '.join(states_per_var)}")