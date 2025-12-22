import subprocess
import pandas as pd
import sys
import itertools

# ==========================================
# CONFIGURATION
# ==========================================
DATASET_FILE = "datasets/WetGrass_test.txt"
# Command to run your existing Simulated Annealing solver
SOLVER_CMD = [sys.executable, "-m", "bnslqa", "solve", DATASET_FILE, "SA", "--reads", "1000"]

# THE QUERY: Count rows where Sprinkler='On' AND Rain='True'
# Based on your data generation: State 0 usually equals 'True'/'On'
QUERY_CONSTRAINTS = {1: 0, 2: 0}  # {Variable_Index: State} -> Var1(Sprinkler)=0, Var2(Rain)=0
HIDDEN_VARS = [0, 3]  # Var0(Cloud) and Var3(WetGrass) are unknown, so we sum over them.

print("==========================================")
print("PHASE 1: RUNNING SA SOLVER")
print("==========================================")

# 1. EXECUTE THE SOLVER
print(f"Executing: {' '.join(SOLVER_CMD)}...")
try:
    # Run the command and capture the text output
    result = subprocess.run(SOLVER_CMD, capture_output=True, text=True)
    output = result.stdout
    # Check if python crashed
    if result.returncode != 0:
        print("CRITICAL ERROR: The solver crashed.")
        print(result.stderr)
        exit(1)
except Exception as e:
    print(f"Error running subprocess: {e}")
    exit(1)

# 2. EXTRACT THE ADJACENCY MATRIX BLINDLY
# We don't check if it's right. We just parse whatever numbers are there.
try:
    # Look for the specific string your tool prints
    matrix_block = output.split("Solution adjacency matrix:")[1].strip().split("\n\n")[0]
    print(f"\n[RAW SOLVER OUTPUT]\n{matrix_block}\n")

    # Parse text "[0, 1, 0]" into python list [0, 1, 0]
    adj_matrix = []
    for line in matrix_block.splitlines():
        # Remove brackets and commas to just get numbers
        clean_line = line.replace('[', '').replace(']', '').replace(',', '')
        if clean_line.strip():
            adj_matrix.append([int(x) for x in clean_line.split()])

    n_vars = len(adj_matrix)

except IndexError:
    print("ERROR: Could not parse the matrix from solver output.")
    print("Did the solver print 'Solution adjacency matrix:'?")
    print("Full Output dump:\n", output)
    exit(1)

# 3. BUILD PARENT MAP
# Convert the matrix into a dictionary: {Child_Index: [Parent_Index, ...]}
parents = {i: [] for i in range(n_vars)}
for r in range(n_vars):  # Row = Parent
    for c in range(n_vars):  # Col = Child
        if adj_matrix[r][c] == 1:
            parents[c].append(r)

print(f"Structure extracted for calculation: {parents}")

print("\n==========================================")
print("PHASE 2: DYNAMIC INFERENCE (NO CHEATING)")
print("==========================================")

# Load the raw data to learn parameters (CPTs) for the structure we just found
# Skip first 2 lines (Header + Problem Name)
try:
    df = pd.read_csv(DATASET_FILE, sep=" ", skiprows=2, header=None)
    total_rows = len(df)
except Exception as e:
    print(f"Error reading dataset: {e}")
    exit(1)


# --- HELPER FUNCTION: GET PROBABILITY FROM DATA ---
# This calculates P(Node=val | Parents=parent_vals) by querying the dataframe directly.
def get_learned_probability(child_idx, child_val, parent_indices, full_state):
    # Case A: No Parents (Marginal Probability)
    if not parent_indices:
        count = len(df[df[child_idx] == child_val])
        return count / total_rows

    # Case B: Has Parents (Conditional Probability)
    # 1. Filter the dataframe to find rows matching the parents' current state
    condition = True
    for p_idx in parent_indices:
        p_val = full_state[p_idx]
        condition &= (df[p_idx] == p_val)

    parent_subset = df[condition]
    parent_count = len(parent_subset)

    # Safety: If this parent combination never appeared in data, Prob is 0
    if parent_count == 0:
        return 0.0

    # 2. Count how many times the child has the target value within that subset
    child_subset = parent_subset[parent_subset[child_idx] == child_val]
    child_count = len(child_subset)

    return child_count / parent_count


# --- MAIN INFERENCE LOOP (CHAIN RULE) ---
# We need P(Query). Since we have hidden variables, we sum over all their possibilities.
# Formula: Σ P(Node|Parents) for all nodes
total_probability_sum = 0.0

# Generate all combinations of states (0, 1) for the hidden variables
# e.g., if Cloud and WetGrass are hidden, we loop: (0,0), (0,1), (1,0), (1,1)
hidden_combinations = itertools.product([0, 1], repeat=len(HIDDEN_VARS))

print("Calculating probability chain...")

for hidden_vals in hidden_combinations:
    # 1. Build the "Current World State"
    # This dictionary represents one specific scenario of the world
    current_world = {}

    # Set the fixed Query values (S=0, R=0)
    for var, val in QUERY_CONSTRAINTS.items():
        current_world[var] = val

    # Set the variable Hidden values
    for i, var in enumerate(HIDDEN_VARS):
        current_world[var] = hidden_vals[i]

    # 2. Calculate Chain Rule for this World
    # P(World) = P(0|Parents) * P(1|Parents) * P(2|Parents) * P(3|Parents)
    world_prob = 1.0

    for node_idx in range(n_vars):
        node_val = current_world[node_idx]
        node_parents = parents[node_idx]

        # Get the parameter from data using the structure the SA found
        p = get_learned_probability(node_idx, node_val, node_parents, current_world)
        world_prob *= p

    # Add this world's probability to the total sum
    total_probability_sum += world_prob

# ==========================================
# PHASE 3: FINAL RESULTS & COMPARISON
# ==========================================

# 1. Calculate Estimated Rows
bn_estimate = int(total_probability_sum * total_rows)

# 2. Calculate Ground Truth (Brute Force Count)
# Count rows where Col 1 is 0 AND Col 2 is 0
true_matches = df[(df[1] == 0) & (df[2] == 0)]
ground_truth = len(true_matches)

# 3. Calculate Independence Estimate (PostgreSQL Style)
# P(S=0) * P(R=0) * Total
p_s = len(df[df[1] == 0]) / total_rows
p_r = len(df[df[2] == 0]) / total_rows
indep_estimate = int(p_s * p_r * total_rows)

print("\n" + "=" * 40)
print("FINAL EXPERIMENT RESULTS")
print("=" * 40)
print(f"Query: SELECT COUNT(*) WHERE Sprinkler='On' AND Rain='True'")
print(f"Total Database Size: {total_rows} rows")
print("-" * 40)

print(f"1. GROUND TRUTH (Actual Count):      {ground_truth}")
print(f"2. POSTGRESQL (Independence Est):    {indep_estimate}")
print(f"   -> Error: {abs(ground_truth - indep_estimate)} rows")

print(f"3. YOUR METHOD (BNSL-QA + SA):       {bn_estimate}")
print(f"   -> Error: {abs(ground_truth - bn_estimate)} rows")

print("-" * 40)
if abs(ground_truth - bn_estimate) < abs(ground_truth - indep_estimate):
    print("CONCLUSION: Your method OUTPERFORMED the standard database approach.")
else:
    print("CONCLUSION: Your method did not outperform the standard approach.")