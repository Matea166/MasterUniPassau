import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bnsl.datasets.grouping_nhanes import category_mappings, encode


def main():
    csv_file = "../bnsl/datasets/data/NHANES_age_prediction.csv"
    df_full = pd.read_csv(csv_file)
    df = encode(df_full)
    mapping_dir = "qa-datasets/mappings"
    os.makedirs(mapping_dir, exist_ok=True)
    for col, mapping in category_mappings(df_full).items():
        pd.DataFrame(
            [
                {"code": code, "category": category}
                for (code, category) in mapping.items()
            ]
        ).to_csv(os.path.join(mapping_dir, f"NHANES_{col}_mapping.csv"), index=False)
    print("First 5 rows of encoded NHANES solver input:")
    print(df.head())
    num_vars = len(df.columns)
    states_per_var = [str(df[col].nunique()) for col in df.columns]
    dummy_length = num_vars * (num_vars - 1)
    dummy_matrix = " ".join(["0"] * dummy_length)
    os.makedirs("qa-datasets", exist_ok=True)
    output_file = "qa-datasets/NHANES_Medical_4vars.txt"
    with open(output_file, "w") as f:
        f.write(f"{num_vars} {' '.join(states_per_var)}\n")
        f.write("NHANES_Medical_4Vars\n")
        f.write(f"{dummy_matrix}\n")
        for index, row in df.iterrows():
            row_str = " ".join(row.astype(str).tolist())
            f.write(f"{row_str}\n")
    print(f"\nSuccess! ALL {len(df)} rows binned and saved to {output_file}")


if __name__ == "__main__":
    main()
