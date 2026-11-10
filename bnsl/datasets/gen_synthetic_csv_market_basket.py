import os

import numpy as np
import pandas as pd


def main():
    items = ["Beer", "Bread", "Cola", "Diapers", "Eggs", "Milk"]
    base_transactions = np.array(
        [
            [0, 1, 0, 0, 0, 1],
            [1, 1, 0, 1, 1, 0],
            [1, 0, 1, 1, 0, 1],
            [1, 1, 0, 1, 0, 1],
            [0, 1, 1, 1, 0, 1],
        ]
    )
    np.random.seed(42)
    num_rows = int(os.environ.get("NUM_ROWS", "100"))
    sampled_indices = np.random.choice(
        len(base_transactions), size=num_rows, replace=True
    )
    generated_matrix = base_transactions[sampled_indices]
    df = pd.DataFrame(generated_matrix, columns=items)
    csv_filename = os.environ.get(
        "CSV_FILENAME", "data/DataMining_MarketBasket_100.csv"
    )
    df.to_csv(csv_filename, index=False)
    print(f"Successfully generated {num_rows} rows based on the textbook templates!")
    print(f"Saved to: {csv_filename}\n")
    print("First 5 rows of the generated dataset:")
    print(df.head())
    print("\nFrequency of each item in the 100 rows:")
    print(df.sum() / num_rows)


if __name__ == "__main__":
    main()
