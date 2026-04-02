import numpy as np
import random
import sys
import os

def generate_saturated_random_dag(n_nodes, max_parents=2):
    matrix = np.zeros((n_nodes, n_nodes), dtype=int)
    nodes = list(range(n_nodes))
    random.shuffle(nodes)
    
    for i, child in enumerate(nodes):
        potential_parents = nodes[:i]
        if potential_parents:
            upper_limit = min(len(potential_parents), max_parents)
            num_parents = random.randint(1, upper_limit)
            parents = random.sample(potential_parents, num_parents)
            for p in parents:
                matrix[p][child] = 1
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

with open(output_file, "w") as f:
    for i in range(num_matrices):
        matrix = generate_saturated_random_dag(num_vars)
        # Convert matrix to Python list string with no line breaks
        matrix_str = str(matrix.tolist())
        f.write(matrix_str + "\n")

print(f"{num_matrices} DAG matrices generated in {output_file}")
