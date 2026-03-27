#!/bin/bash

# --- PROGRESS BAR FUNCTION ---
progress_bar() {
    local current=$1
    local total=$2
    local start_time=$3
    local current_time=$(date +%s)
    local elapsed=$((current_time - start_time))
    local eta=0

    if [ $current -gt 0 ]; then
        eta=$((elapsed * (total - current) / current))
    fi

    local progress=$((current * 20 / total))
    local bar=$(printf "%-${progress}s" "#" | sed 's/ /#/g')
    local empty=$(printf "%-$((20 - progress))s" "-")

    printf "\rProgress: [%s%s] %d/%d | Elapsed: %ds | ETA: %ds " "$bar" "$empty" "$current" "$total" "$elapsed" "$eta"
}

# --- 1. SELECTION MENU ---
echo "=== BNSL-QA-PYTHON AUTOMATION PIPELINE ==="

echo "Select a dataset from /datasets:"
select dataset_path in qa-datasets/*; do
    if [ -n "$dataset_path" ]; then
        dataset_name=$(basename "$dataset_path" | cut -d. -f1)
        break
    else
        echo "Invalid option."
    fi
done

echo ""
echo "Select Solver:"
select solver in "SA" "SQA"; do
    if [ -n "$solver" ]; then break; else echo "Invalid option."; fi
done

echo ""
read -p "Enter number of trials: " executions
read -p "Enter number of annealing reads: " reads

timestamp=$(date +"%Y-%m-%d_%H-%M-%S")

# --- 2. SOLVER EXECUTION ---
solver_out_base="dispatch_output/solver_outputs/${solver}"
solver_run_dir="${solver_out_base}/${solver}_Matrix_${dataset_name}_${executions}_${reads}_${timestamp}"
mkdir -p "$solver_run_dir"
matrix_file="${solver_run_dir}/adjacency_matrix.txt"

echo -e "\nRunning $solver solver $executions times..."
start_time=$(date +%s)
progress_bar 0 $executions $start_time

for i in $(seq 1 $executions); do
    python -m bnslqa solve "$dataset_path" $solver --reads $reads >> "$matrix_file" 2>&1
    progress_bar $i $executions $start_time
done
echo -e "\nOutputs saved to: $matrix_file"

# --- 3. EXTRACT UNIQUE MATRICES ---
unique_matrix_file="${solver_run_dir}/unique_adjacency_matrix.txt"
python -c "
import re
with open('$matrix_file', 'r') as f: data = f.read()

# Pattern to find 'Solution adjacency matrix:' followed by the bracketed lines
pattern = r'Solution adjacency matrix:\n((?:\[.*?\]\n?)+)'
matches = re.findall(pattern, data)

unique_matrices = set()
for match in matches:
    lines = match.strip().split('\n')
    matrix_str = '[' + ', '.join(lines) + ']'
    unique_matrices.add(matrix_str)

with open('$unique_matrix_file', 'w') as f:
    for m in unique_matrices: f.write(m + '\n')
"
num_matrices=$(wc -l < "$unique_matrix_file")
echo "Found $num_matrices unique matrices."

# --- 4. SELECT ESTIMATION SCRIPT ---
echo -e "\nSelect the cardinality estimation script:"
select py_script in cardinality_estimation/cardinality_estimation_*.py; do
    if [ -n "$py_script" ]; then break; else echo "Invalid option."; fi
done

# --- 5. RUN CARDINALITY ESTIMATION ---
card_out_dir="dispatch_output/cardinality_estimation_outputs/${solver}-results/${solver}-results_${dataset_name}_${reads}_${timestamp}"
mkdir -p "$card_out_dir"

echo "current_path $(pwd)"

echo -e "\nProcessing cardinality estimation for $num_matrices matrices..."
start_time=$(date +%s)
progress_bar 0 $num_matrices $start_time

counter=1
while IFS= read -r matrix; do
    # Passing matrix string, output directory, and graph ID
    python "$py_script" "$matrix" "$card_out_dir" "$counter" > /dev/null 2>&1
    progress_bar $counter $num_matrices $start_time
    counter=$((counter + 1))
done < "$unique_matrix_file"
echo -e "\nGraphs and intermediate CSVs saved to: $card_out_dir"

# --- 6. FINAL RESULTS MERGE ---
results_dir="dispatch_output/results"
mkdir -p "$results_dir"
final_csv="${results_dir}/final_queriescardinality_${solver}_${dataset_name}_${reads}_${timestamp}.csv"

echo "Merging all results into final CSV..."
python -c "
import pandas as pd, glob, os, re
csv_files = glob.glob(os.path.join('$card_out_dir', 'graph_*_cardinality.csv'))
if not csv_files:
    print('No valid results found to merge.')
    exit()

# Sort files numerically by the graph index extracted from the filename
csv_files.sort(key=lambda x: int(re.search(r'graph_(\d+)', x).group(1)))

# Start with the first available file
df_final = pd.read_csv(csv_files[0])
# Rename cardinality column to the name of the first found graph
first_id = re.search(r'graph_(\d+)', csv_files[0]).group(1)
df_final = df_final.rename(columns={'estimated_cardinality': f'Graph_{first_id}.png'})

for file in csv_files[1:]:
    graph_id = re.search(r'graph_(\d+)', file).group(1)
    df_temp = pd.read_csv(file).rename(columns={'estimated_cardinality': f'Graph_{graph_id}.png'})
    df_final = pd.merge(df_final, df_temp, on='query_sql')

df_final.to_csv('$final_csv', index=False)
"
echo "Process complete! Final report: $final_csv"