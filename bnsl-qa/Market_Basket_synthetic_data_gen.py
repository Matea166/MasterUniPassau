import pandas as pd
import os


csv_filename = "../bnsl/datasets/data/DataMining_MarketBasket_100.csv"
df = pd.read_csv(csv_filename)

print(f"Loaded {len(df)} rows from {csv_filename}")

#Prepare the BNSLQA solver header
num_vars = len(df.columns)
states_per_var = ["2"] * num_vars  # Every item is binary (0 or 1)


# Create the dummy adjacency-matrix placeholder.
# Its length is num_vars * (num_vars - 1).

dummy_length = num_vars * (num_vars - 1)
dummy_matrix = " ".join(["0"] * dummy_length)


os.makedirs("qa-datasets", exist_ok=True)
output_file = "qa-datasets/MarketBasket100.txt"

with open(output_file, 'w') as f:

    f.write(f"{num_vars} {' '.join(states_per_var)}\n")


    f.write("DataMining100\n")


    f.write(f"{dummy_matrix}\n")


    for index, row in df.iterrows():
        row_str = " ".join(row.astype(str).tolist())
        f.write(f"{row_str}\n")

print(f"Success! Formatted data saved to {output_file}")
