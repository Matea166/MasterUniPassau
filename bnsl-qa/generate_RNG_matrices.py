import numpy as np
import random
import sys
import os

random.seed(42)

def generate_random_dag(n_nodes, max_parents=2):
    matrix = np.zeros((n_nodes, n_nodes), dtype=int)

    # Random topological order guarantees acyclicity.
    nodes = list(range(n_nodes))
    random.shuffle(nodes)

    for i, child in enumerate(nodes):
        potential_parents = nodes[:i]

        if potential_parents:
            upper_limit = min(len(potential_parents), max_parents)
            num_parents = random.randint(0, upper_limit)
            parents = random.sample(potential_parents, num_parents)

            for parent in parents:
                matrix[parent][child] = 1

    return matrix

# -----------------------------
# ARGUMENTS FROM SHELL
# -----------------------------
if len(sys.argv) < 4:
    print("Usage: python generate_RNG_matrices.py <num_vars> <num_matrices> <output_dir>")
    sys.exit(1)

num_vars = int(sys.argv[1])
num_matrices = int(sys.argv[2])
output_dir = sys.argv[3]

os.makedirs(output_dir, exist_ok=True)

output_file = os.path.join(output_dir, f"RNG_matrix_{num_matrices}_{num_vars}.txt")

seen = set()
unique_matrices = []

for _ in range(num_matrices):
    matrix = generate_random_dag(num_vars, max_parents=2)
    key = tuple(matrix.flatten().tolist())

    if key not in seen:
        seen.add(key)
        unique_matrices.append(matrix)

with open(output_file, "w") as f:
    for matrix in unique_matrices:
        matrix_str = str(matrix.tolist())
        f.write(matrix_str + "\n")

print(f"{num_matrices} random DAG candidates generated.")
print(f"{len(unique_matrices)} unique DAG matrices written to {output_file}")
