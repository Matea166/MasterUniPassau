import pandas as pd
import json
from collections import Counter


PATH=""
CSV_FILE = PATH
OUTPUT_JSON = "child_cpt.json"

PARENT1_COLUMN = "age_group"
PARENT2_COLUMN = "BMXBMI"
CHILD_COLUMN = "DIQ010"

ALPHA = 1.0

BMI_STATES = ["Underweight (<18.5)",
              "Normal(18.5-25)",
              "Overweight(25-30)",
              "Obese(>30)"]

DIQ_STATES = ["1.0", "2.0", "3.0"]


df = pd.read_csv(CSV_FILE)


def bmi_bucket(bmi):
    if pd.isna(bmi):
        return None
    if bmi < 18.5:
        return BMI_STATES[0]
    elif bmi < 25:
        return BMI_STATES[1]
    elif bmi < 30:
        return BMI_STATES[2]
    else:
        return BMI_STATES[3]

df["parent1_state"] = df[PARENT1_COLUMN]
df["parent2_state"] = df[PARENT2_COLUMN].apply(bmi_bucket)
df["child_state"] = df[CHILD_COLUMN].astype(str)


parent1_states = sorted(df["parent1_state"].dropna().unique())
parent2_states = BMI_STATES
child_states = DIQ_STATES


cpt = []

for p1 in parent1_states:

    level_2 = []

    for p2 in parent2_states:

        subset = df[
            (df["parent1_state"] == p1) &
            (df["parent2_state"] == p2)
        ]["child_state"].dropna()

        counts = Counter(subset)
        N = sum(counts.values())
        K = len(child_states)

        row = [
            round((counts.get(state, 0) + ALPHA) / (N + ALPHA * K), 6)
            for state in child_states
        ]

        level_2.append(row)

    cpt.append(level_2)


output = {
    "states": child_states,
    "parents": [PARENT1_COLUMN, PARENT2_COLUMN],
    "cpt": cpt
}

with open(OUTPUT_JSON, "w") as f:
    json.dump(output, f, indent=2)

print(f"CPT saved to {OUTPUT_JSON}")
