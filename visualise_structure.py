import sys
import subprocess
import networkx as nx
import matplotlib.pyplot as plt

# --- CONFIGURATION ---
# We use the evaluation dataset we just created
DATASET_FILE = "datasets/Movie_Eval.txt"
SOLVER_CMD = [sys.executable, "-m", "bnslqa", "solve", DATASET_FILE, "SA", "--reads", "1000"]

print("1. Running solver to fetch structure...")
process = subprocess.run(SOLVER_CMD, capture_output=True, text=True)
output = process.stdout

if "Solution adjacency matrix:" in output:
    # Extract the text block containing the matrix
    matrix_str = output.split("Solution adjacency matrix:")[1].strip().split("\n\n")[0]
    print(f"   Raw Matrix Output:\n{matrix_str}")

    # --- ROBUST PARSING FIX ---
    # 1. Split into lines
    rows = matrix_str.strip().split('\n')
    adj_matrix = []

    for r in rows:
        # 2. Remove brackets and commas, then split by space
        clean_row = r.replace('[', '').replace(']', '').replace(',', ' ')
        # 3. Convert to integers
        int_row = [int(x) for x in clean_row.split()]
        adj_matrix.append(int_row)
    # --------------------------

    # Draw Graph
    G = nx.DiGraph()
    # Node 0 is Kind (Genre), Node 1 is YearBin
    labels = {0: "Kind (Genre)", 1: "Year (>2010)"}

    edge_found = False
    for r in range(len(adj_matrix)):
        for c in range(len(adj_matrix)):
            if adj_matrix[r][c] == 1:
                G.add_edge(labels[r], labels[c])
                edge_found = True

    if edge_found:
        print(f"2. Edges found: {G.edges()}")

        # Plot
        plt.figure(figsize=(6, 4))
        pos = nx.spring_layout(G)
        nx.draw(G, pos, with_labels=True, node_color='lightblue', node_size=3000, arrowsize=30, font_weight='bold')
        plt.title("Learned Bayesian Network Structure")

        output_img = "structure_viz.png"
        plt.savefig(output_img)
        print(f"3. Success! Graph saved to '{output_img}'")
        print("   Open this image to see if the arrow points Year -> Kind!")
    else:
        print("2. Solver returned an empty graph (Independence). No edges to draw.")

else:
    print("Error: Solver failed or did not output a matrix.")
    print("Full Output:\n", output)