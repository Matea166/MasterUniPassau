import pandas as pd
import os

# 1. Load the CSV
csv_file = "../bnsl/datasets/data/NHANES_age_prediction.csv"
df_full = pd.read_csv(csv_file)

# Keep ONLY the 4 columns
keep_cols = ['age_group', 'BMXBMI', 'RIAGENDR', 'DIQ010']
df = df_full[keep_cols].copy()

# ==========================================
# 2.  (WHO Medical Bins)
# ==========================================
# Binning BMI into 4 medical categories (0, 1, 2, 3)
bins = [0, 18.5, 25.0, 30.0, 150.0]
labels = [0, 1, 2, 3]
df['BMXBMI'] = pd.cut(df['BMXBMI'], bins=bins, labels=labels, right=False).astype(int)

mapping_dir = "qa-datasets/mappings"
os.makedirs(mapping_dir, exist_ok=True)

for col in ['age_group', 'RIAGENDR', 'DIQ010']:
    categories = df[col].astype('category').cat.categories
    mapping = dict(enumerate(categories))

    pd.DataFrame(
        [{"code": code, "category": category} for code, category in mapping.items()]
    ).to_csv(os.path.join(mapping_dir, f"NHANES_{col}_mapping.csv"), index=False)


# 3. Encode non-BMI categorical variables
df['age_group'] = df['age_group'].astype('category').cat.codes
df['RIAGENDR'] = df['RIAGENDR'].astype('category').cat.codes
df['DIQ010'] = df['DIQ010'].astype('category').cat.codes

print("First 5 rows of encoded NHANES solver input:")
print(df.head())

# ==========================================
# 4. PREPARE THE BNSLQA FORMAT
# ==========================================
num_vars = len(df.columns)
states_per_var = [str(df[col].nunique()) for col in df.columns]

# Dummy matrix of 12 zeros for the SA solver target
dummy_length = num_vars * (num_vars - 1)
dummy_matrix = " ".join(["0"] * dummy_length)

os.makedirs("qa-datasets", exist_ok=True)
output_file = "qa-datasets/NHANES_Medical_4vars.txt"

with open(output_file, 'w') as f:

    f.write(f"{num_vars} {' '.join(states_per_var)}\n")
    f.write("NHANES_Medical_4Vars\n")
    f.write(f"{dummy_matrix}\n")
    
    for index, row in df.iterrows():
        row_str = " ".join(row.astype(str).tolist())
        f.write(f"{row_str}\n")

print(f"\nSuccess! ALL {len(df)} rows binned and saved to {output_file}")
