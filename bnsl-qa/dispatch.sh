#!/bin/bash


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

NONINTERACTIVE=0
if [ -n "${DATASET_TXT:-}" ] && [ -n "${SOLVER:-}" ] && [ -n "${TRIALS:-}" ] && [ -n "${READS:-}" ] && [ -n "${CE_SCRIPT:-}" ]; then
    NONINTERACTIVE=1
fi

echo "=== BNSL-QA-PYTHON AUTOMATION PIPELINE ==="

if [ "$NONINTERACTIVE" = "1" ]; then
    mode="Run solver now"
else
    echo ""
    echo "Select pipeline mode:"
    select mode in "Run solver now" "Use previous unique matrices"; do
        if [ -n "$mode" ]; then
            break
        else
            echo "Invalid option."
        fi
    done
fi

timestamp=$(date +"%Y-%m-%d_%H-%M-%S")

if [ "$mode" = "Run solver now" ]; then

    if [ "$NONINTERACTIVE" = "1" ]; then
        dataset_path="$DATASET_TXT"
        if [ ! -f "$dataset_path" ]; then
            echo "Error: dataset TXT file not found: $dataset_path"
            exit 1
        fi
        dataset_name=$(basename "$dataset_path" | cut -d. -f1)
        solver="$SOLVER"
        executions="$TRIALS"
        reads="$READS"
        echo "Dataset: $dataset_path | Solver: $solver | Trials: $executions | Reads: $reads"
    else
        echo "Select a dataset from /datasets:"
        select dataset_path in qa-datasets/*.txt; do
            if [ -n "$dataset_path" ]; then
                dataset_name=$(basename "$dataset_path" | cut -d. -f1)
                break
            else
                echo "Invalid option."
            fi
        done

        echo ""
        echo "Select Solver:"
        select solver in "SA" "SQA" "QAOA"; do
            if [ -n "$solver" ]; then break; else echo "Invalid option."; fi
        done

        echo ""
        read -p "Enter number of trials: " executions
        read -p "Enter number of annealing reads: " reads
    fi

    solver_out_base="dispatch_output/solver_outputs/${solver}"
    solver_run_dir="${solver_out_base}/${solver}_Matrix_${dataset_name}_${executions}_${reads}_${timestamp}"
    mkdir -p "$solver_run_dir"
    matrix_file="${solver_run_dir}/adjacency_matrix.txt"

    echo -e "\nRunning $solver solver $executions times..."
    start_time=$(date +%s)
    progress_bar 0 $executions $start_time

    for i in $(seq 1 $executions); do
        solver_args=(--reads "$reads")
        if [ "$solver" = "QAOA" ]; then
            qaoa_output="${QAOA_RESULTS_DIR:-../results/qaoa/${dataset_name}_${executions}_${reads}_${timestamp}}"
            solver_args=(--shots "${QAOA_SHOTS:-$reads}" --reps "${QAOA_REPS:-1}"
                         --final-shots "${QAOA_FINAL_SHOTS:-${QAOA_SHOTS:-$reads}}"
                         --seed "$(( ${QAOA_SEED:-42} + i - 1 ))"
                         --qaoa-backend "${QAOA_BACKEND:-aer}"
                         --qaoa-output "$qaoa_output/trial_${i}.json")
            if [ -n "${QAOA_MAXITER:-}" ]; then
                solver_args+=(--maxiter "$QAOA_MAXITER")
            fi
            if [ "${QAOA_BACKEND:-aer}" = "ibm" ]; then
                [ -z "${IBM_BACKEND:-}" ] || solver_args+=(--ibm-backend "$IBM_BACKEND")
                [ -z "${IBM_INSTANCE:-}" ] || solver_args+=(--ibm-instance "$IBM_INSTANCE")
                [ -z "${IBM_API_KEY_FILE:-}" ] || solver_args+=(--ibm-api-key-file "$IBM_API_KEY_FILE")
            fi
        fi
        solver_status=0
        python3 -m bnslqa solve "$dataset_path" "$solver" "${solver_args[@]}" >> "$matrix_file" 2>&1 || solver_status=$?
        if [ "$solver_status" -ne 0 ]; then
            if [ "$solver" = "QAOA" ] && [ "$solver_status" -eq 3 ]; then
                echo -e "\nQAOA trial $i rejected: invalid minimum-energy graph; continuing scheduled trials."
            else
                echo "Error: $solver failed on trial $i; see $matrix_file" >&2
                exit 1
            fi
        fi
        progress_bar $i $executions $start_time
    done
    echo -e "\nOutputs saved to: $matrix_file"

    unique_matrix_file="${solver_run_dir}/unique_adjacency_matrix.txt"
    python -c "
import re
with open('$matrix_file', 'r') as f: data = f.read()

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

else

    echo ""
    echo "Select a previous unique_adjacency_matrix.txt file:"

    previous_unique_files=()
    while IFS= read -r file; do
        previous_unique_files+=("$file")
    done < <(find dispatch_output/solver_outputs -type f -name "unique_adjacency_matrix.txt" 2>/dev/null | sort)

    if [ ${#previous_unique_files[@]} -eq 0 ]; then
        echo "No previous unique_adjacency_matrix.txt files found."
        echo "You need to run the solver at least once first."
        exit 1
    fi

    select unique_matrix_file in "${previous_unique_files[@]}"; do
        if [ -n "$unique_matrix_file" ]; then
            solver_run_dir=$(dirname "$unique_matrix_file")
            solver=$(basename "$(dirname "$solver_run_dir")")
            run_folder=$(basename "$solver_run_dir")
            break
        else
            echo "Invalid option."
        fi
    done

    echo ""
    echo "Using previous unique matrices from:"
    echo "$unique_matrix_file"

    if [[ "$run_folder" =~ ^${solver}_Matrix_(.*)_([0-9]+)_([0-9]+)_([0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2})$ ]]; then
        dataset_name="${BASH_REMATCH[1]}"
        executions="${BASH_REMATCH[2]}"
        reads="${BASH_REMATCH[3]}"
    else
        dataset_name="$run_folder"
        reads="previous"
    fi

fi

if [ "$mode" != "Run solver now" ]; then
    python3 - "$unique_matrix_file" <<'PY' || exit 1
import ast
import sys
import networkx as nx

with open(sys.argv[1]) as f:
    matrices = f.readlines()
valid_matrices = []
for line in matrices:
    matrix = ast.literal_eval(line)
    graph = nx.DiGraph((i, j) for i, row in enumerate(matrix)
                      for j, value in enumerate(row) if value == 1)
    if nx.is_directed_acyclic_graph(graph) and all(degree <= 2 for _, degree in graph.in_degree()):
        valid_matrices.append(line)
with open(sys.argv[1], 'w') as f:
    f.writelines(valid_matrices)
PY
fi

if [ ! -s "$unique_matrix_file" ]; then
    echo "Error: no valid graphs to evaluate." >&2
    exit 1
fi

num_matrices=$(wc -l < "$unique_matrix_file")
echo "Found $num_matrices unique matrices."

if [ "$NONINTERACTIVE" = "1" ]; then
    py_script="$CE_SCRIPT"
    if [ ! -f "$py_script" ]; then
        echo "Error: cardinality estimation script not found: $py_script"
        exit 1
    fi
else
    echo -e "\nSelect the cardinality estimation script:"
    select py_script in cardinality_estimation/cardinality_estimation_*.py; do
        if [ -n "$py_script" ]; then break; else echo "Invalid option."; fi
    done
fi

card_out_dir="dispatch_output/cardinality_estimation_outputs/${solver}-results/${solver}-results_${dataset_name}_${reads}_${timestamp}"
mkdir -p "$card_out_dir"

echo -e "\nProcessing cardinality estimation for $num_matrices matrices..."
start_time=$(date +%s)
progress_bar 0 $num_matrices $start_time

counter=1
while IFS= read -r matrix; do
    graph_log="$card_out_dir/graph_${counter}_inference.log"
    printf '%s\n' "$matrix" > "$card_out_dir/Graph_${counter}.txt"
    if ! python3 "$py_script" "$matrix" "$card_out_dir" "$counter" > "$graph_log" 2>&1; then
        echo -e "\nError: cardinality estimation failed for graph $counter. See $graph_log" >&2
        cat "$graph_log" >&2
        exit 1
    fi
    progress_bar $counter $num_matrices $start_time
    counter=$((counter + 1))
done < "$unique_matrix_file"
echo -e "\nGraphs and intermediate CSVs saved to: $card_out_dir"

results_dir="dispatch_output/results"
mkdir -p "$results_dir"
final_csv="${results_dir}/final_queriescardinality_${solver}_${dataset_name}_${reads}_${timestamp}.csv"

echo "Merging all results into final CSV..."
python3 -c "
import pandas as pd, glob, os, re, math
csv_files = glob.glob(os.path.join('$card_out_dir', 'graph_*_cardinality.csv'))
if not csv_files:
    raise ValueError('No valid results found to merge.')

def read_estimates(file):
    frame = pd.read_csv(file)
    if frame.empty or frame['query_sql'].isna().any() or frame['query_sql'].duplicated().any():
        raise ValueError(f'Empty or duplicate queries in {file}')
    values = pd.to_numeric(frame['estimated_cardinality'], errors='raise')
    if values.isna().any() or (values < 0).any() or not values.map(math.isfinite).all():
        raise ValueError(f'Invalid cardinalities in {file}')
    return frame

csv_files.sort(key=lambda x: int(re.search(r'graph_(\d+)', x).group(1)))

df_final = read_estimates(csv_files[0])
first_id = re.search(r'graph_(\d+)', csv_files[0]).group(1)
df_final = df_final.rename(columns={'estimated_cardinality': f'Graph_{first_id}.png'})

for file in csv_files[1:]:
    graph_id = re.search(r'graph_(\d+)', file).group(1)
    df_temp = read_estimates(file).rename(columns={'estimated_cardinality': f'Graph_{graph_id}.png'})
    if set(df_final['query_sql']) != set(df_temp['query_sql']):
        raise ValueError(f'Query mismatch in {file}')
    df_final = pd.merge(df_final, df_temp, on='query_sql', validate='one_to_one')

df_final.to_csv('$final_csv', index=False)
" || exit 1
echo "Process complete! Final report: $final_csv"

graph_dir="../results/graphs/${solver}_Matrix_${dataset_name}_${executions:-previous}_${reads}_${timestamp}"
mkdir -p "$graph_dir/matrices" "$graph_dir/graphs" || exit 1
cp -R "$solver_run_dir/." "$graph_dir/matrices/" || exit 1
cp -R "$card_out_dir/." "$graph_dir/graphs/" || exit 1

echo "DISPATCH_GRAPH_DIR=$graph_dir"
echo "DISPATCH_SOLVER_DIR=$solver_run_dir"
echo "DISPATCH_CARD_DIR=$card_out_dir"
echo "DISPATCH_FINAL_CSV=$final_csv"
