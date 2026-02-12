import pandas as pd
import json
from collections import Counter

PATH=""
CSV_FILE = PATH
OUTPUT_JSON = "movie_link_cpt.json"

PARENT_COLUMN = "movie_id"
CHILD_COLUMN = "linked_movie_id"
ALPHA = 1.0

BUCKET_STATES = [
    "movie_rare",
    "movie_medium",
    "movie_frequent",
    "movie_very_frequent"
]
# ----------------------------

df = pd.read_csv(CSV_FILE)

# ---------- BUCKET FUNCTION ----------
def build_bucket_function(series):
    counts = series.value_counts()

    def bucket(val):
        if pd.isna(val):
            return None
        c = counts.get(val, 0)
        if c < 5:
            return "movie_rare"
        elif c < 20:
            return "movie_medium"
        elif c < 100:
            return "movie_frequent"
        else:
            return "movie_very_frequent"

    return bucket


parent_bucket_fn = build_bucket_function(df[PARENT_COLUMN])
child_bucket_fn = build_bucket_function(df[CHILD_COLUMN])

df["parent_bucket"] = df[PARENT_COLUMN].apply(parent_bucket_fn)
df["child_bucket"] = df[CHILD_COLUMN].apply(child_bucket_fn)

# ---------- CPT ----------
cpt_matrix = []

for parent_state in BUCKET_STATES:

    subset = df[df["parent_bucket"] == parent_state]["child_bucket"].dropna()

    counts = Counter(subset)
    N = sum(counts.values())
    K = len(BUCKET_STATES)

    row = [
        round((counts.get(child_state, 0) + ALPHA) / (N + ALPHA * K), 12)
        for child_state in BUCKET_STATES
    ]

    cpt_matrix.append(row)

# ---------- OUTPUT ----------
output = {
    "states": BUCKET_STATES,
    "parents": ["movie_id"],
    "cpt": cpt_matrix
}

with open(OUTPUT_JSON, "w") as f:
    json.dump(output, f, indent=2)

print(f"CPT saved to {OUTPUT_JSON}")
