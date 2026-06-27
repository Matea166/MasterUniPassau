#!/usr/bin/env bash

BASE_DIR="RNG_Matrix"
MATRIX_DIR="$BASE_DIR/matrices"
RESULT_DIR="$BASE_DIR/results"

mkdir -p "$MATRIX_DIR" "$RESULT_DIR"

while true; do
    echo ""
    echo "==== RNG MATRIX PIPELINE ===="
    echo "1) Generate matrices"
    echo "2) Run cardinality estimation"
    echo "3) Exit"
    read -r -p "Choose an option: " choice

    # ----------------------------
    # OPTION 1: GENERATE MATRICES
    # ----------------------------
    if [ "$choice" == "1" ]; then
        read -r -p "Number of variables: " NUM_VARS
        read -r -p "Number of matrices: " NUM_MATRICES

        echo "Generating DAG matrices..."
        python3 generate_RNG_matrices.py "$NUM_VARS" "$NUM_MATRICES" "$MATRIX_DIR"

        echo "Done. Returning to menu..."

    # ----------------------------
    # OPTION 2: RUN CARDINALITY
    # ----------------------------
    elif [ "$choice" == "2" ]; then

        # Select cardinality estimation script
        echo ""
        echo "Select a cardinality estimation script:"
        scripts=(cardinality_estimation/cardinality_estimation_*.py)

        if [ ${#scripts[@]} -eq 0 ]; then
            echo "No cardinality_estimation_*.py files found."
            continue
        fi
        for i in "${!scripts[@]}"; do
            echo "$((i+1))) ${scripts[$i]}"
        done
        read -r -p "Option: " script_choice
        CARD_SCRIPT=${scripts[$((script_choice-1))]}

        # Select matrix file
        echo ""
        echo "Select a matrix file:"
        matrices=($MATRIX_DIR/*.txt)
        if [ ${#matrices[@]} -eq 0 ]; then
            echo "No matrix files found."
            continue
        fi
        for i in "${!matrices[@]}"; do
            echo "$((i+1))) $(basename "${matrices[$i]}")"
        done
        read -r -p "Option: " matrix_choice
        MATRIX_FILE=${matrices[$((matrix_choice-1))]}

        # Output directory for this run
        TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
        OUTPUT_DIR="$RESULT_DIR/run_$TIMESTAMP"
        mkdir -p "$OUTPUT_DIR"

        echo ""
        echo "Running cardinality estimation on all matrices..."

        index=1
        while IFS= read -r matrix || [ -n "$matrix" ]; do
            if [ -z "$matrix" ]; then
                continue
            fi
            echo "Processing matrix $index..."
            python3 "$CARD_SCRIPT" "$matrix" "$OUTPUT_DIR" "$index"
            ((index++))
        done < "$MATRIX_FILE"

        # Combine all CSVs into a single final CSV
        echo "Combining CSV results..."
        python3 - <<EOF
import os
import glob
import pandas as pd

output_dir = "$OUTPUT_DIR"
csv_files = sorted(glob.glob(os.path.join(output_dir, "*_cardinality.csv")))

if len(csv_files) == 0:
    print("No CSV files found to combine.")
    exit(0)

# Read first CSV
df_final = pd.read_csv(csv_files[0])
df_final.columns = ["query_sql", f"matrix_1"]

# Merge remaining CSVs
for i, csv in enumerate(csv_files[1:], start=2):
    df = pd.read_csv(csv)
    df_final[f"matrix_{i}"] = df["estimated_cardinality"]

final_csv = os.path.join(output_dir, "final_queries_cardinality.csv")
df_final.to_csv(final_csv, index=False)
print(f"Final CSV saved to: {final_csv}")
EOF

        echo "All done. Results in: $OUTPUT_DIR"

    # ----------------------------
    # EXIT
    # ----------------------------
    elif [ "$choice" == "3" ]; then
        echo "Exiting..."
        break
    else
        echo "Invalid option."
    fi
done
