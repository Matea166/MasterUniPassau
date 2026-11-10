import os

import pandas as pd


def main():
    csv_filename = os.environ.get(
        "CSV_FILENAME", "../bnsl/datasets/data/DataMining_MarketBasket_100.csv"
    )
    df = pd.read_csv(csv_filename)
    print(f"Loaded {len(df)} rows from {csv_filename}")
    num_vars = len(df.columns)
    states_per_var = ["2"] * num_vars
    dummy_length = num_vars * (num_vars - 1)
    dummy_matrix = " ".join(["0"] * dummy_length)
    os.makedirs("qa-datasets", exist_ok=True)
    output_file = os.environ.get("OUTPUT_FILE", "qa-datasets/MarketBasket100.txt")
    with open(output_file, "w") as f:
        f.write(f"{num_vars} {' '.join(states_per_var)}\n")
        f.write("DataMining100\n")
        f.write(f"{dummy_matrix}\n")
        for index, row in df.iterrows():
            row_str = " ".join(row.astype(str).tolist())
            f.write(f"{row_str}\n")
    print(f"Success! Formatted data saved to {output_file}")


if __name__ == "__main__":
    main()
