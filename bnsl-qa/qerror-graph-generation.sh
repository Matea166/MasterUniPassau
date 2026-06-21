#!/usr/bin/env bash

BASE_DIR="./dispatch_output/solver_outputs"
OUTPUT_BASE="q-error_output"
CARD_RESULTS_DIR="../bnsl/card_results"

mkdir -p "$OUTPUT_BASE"

timestamp=$(date +"%Y-%m-%d_%H-%M-%S")

echo "==============================="
echo " Select Result Files"
echo "==============================="

declare -a sa_files
declare -a sqa_files

while true; do

    echo "==============================="
    echo " Select SA result file"
    echo "==============================="
    mapfile -t sa_files_tmp < <(find "$OUTPUT_BASE" -maxdepth 1 -name "*SA*.csv")

    select sa_file in "${sa_files_tmp[@]}"; do
        if [[ -n "$sa_file" ]]; then
            sa_files+=("$sa_file")
            break
        else
            echo "Invalid selection"
        fi
    done

    echo "==============================="
    echo " Select SQA result file"
    echo "==============================="
    mapfile -t sqa_files_tmp < <(find "$OUTPUT_BASE" -maxdepth 1 -name "*SQA*.csv")

    select sqa_file in "${sqa_files_tmp[@]}"; do
        if [[ -n "$sqa_file" ]]; then
            sqa_files+=("$sqa_file")
            break
        else
            echo "Invalid selection"
        fi
    done

    echo "Add another SA/SQA pair? (y/n)"
    read -r add_more
    if [[ "$add_more" != "y" ]]; then
        break
    fi

done

echo "==============================="
echo " Select card_results CSV"
echo "==============================="

mapfile -t card_files < <(find "$CARD_RESULTS_DIR" -maxdepth 1 -name "*_final.csv")

select card_file in "${card_files[@]}"; do
    if [[ -n "$card_file" ]]; then
        break
    else
        echo "Invalid selection"
    fi
done

# Save selected pairs
pairs_file="$OUTPUT_BASE/selected_sa_sqa_pairs_${timestamp}.txt"

for i in "${!sa_files[@]}"; do
    echo "${sa_files[$i]} ${sqa_files[$i]}" >> "$pairs_file"
done

echo "Selected pairs saved to: $pairs_file"

echo "Running graph generator..."

python3 qerror-graph-generation.py "$pairs_file" "$card_file"

echo "================================"
echo "Finished"
echo "Graph generated in q-error_output"
echo "================================"
