import pandas as pd
import numpy as np

#Define the items as they appear in the textbook
items = ['Beer', 'Bread', 'Cola', 'Diapers', 'Eggs', 'Milk']

#Define the 5 base transactions from the textbook as a binary matrix
#Matrix order: [Beer, Bread, Cola, Diapers, Eggs, Milk]
base_transactions = np.array([
    [0, 1, 0, 0, 0, 1],  # T1: Bread, Milk
    [1, 1, 0, 1, 1, 0],  # T2: Beer, Bread, Diapers, Eggs
    [1, 0, 1, 1, 0, 1],  # T3: Beer, Cola, Diapers, Milk
    [1, 1, 0, 1, 0, 1],  # T4: Beer, Bread, Diapers, Milk
    [0, 1, 1, 1, 0, 1]   # T5: Bread, Cola, Diapers, Milk
])

#Generate 100 rows by randomly sampling from the 5 base transactions

np.random.seed(42)
num_rows = 100

#Randomly pick indices from 0 to 4, 100 times
sampled_indices = np.random.choice(len(base_transactions), size=num_rows, replace=True)

#Build the final 100-row matrix
generated_matrix = base_transactions[sampled_indices]


df = pd.DataFrame(generated_matrix, columns=items)


csv_filename = "data/DataMining_MarketBasket_100.csv"
df.to_csv(csv_filename, index=False)

print(f"Successfully generated {num_rows} rows based on the textbook templates!")
print(f"Saved to: {csv_filename}\n")

print("First 5 rows of the generated dataset:")
print(df.head())

print("\nFrequency of each item in the 100 rows:")
print(df.sum() / num_rows)