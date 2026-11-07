#!/usr/bin/env bash

# Random-structure robustness check: generates random acyclic adjacency
# matrices and evaluates them with a cardinality-estimation script.
#
# Non-interactive mode (used by scripts/run_*.sh): set RNG_ACTION to
#   generate  with NUM_VARS and NUM_MATRICES set, or
#   estimate  with CARD_SCRIPT and MATRIX_FILE set
# to run one action and exit. Leave RNG_ACTION unset for the interactive
# menu. In estimate mode the last output line is a machine-readable
# RNG_OUTPUT_DIR path for orchestration scripts.

BASE_DIR="RNG_Matrix"
MATRIX_DIR="$BASE_DIR/matrices"
RESULT_DIR="$BASE_DIR/results"

mkdir -p "$MATRIX_DIR" "$RESULT_DIR"

generate_matrices() {
    local num_vars=$1
    local num_matrices=$2

    echo "Generating DAG matrices..."
    python3 generate_RNG_matrices.py "$num_vars" "$num_matrices" "$MATRIX_DIR"
}

run_estimation() {
    local card_script=$1
    local matrix_file=$2

    if [ ! -f "$card_script" ]; then
        echo "Error: cardinality estimation script not found: $card_script"
        return 1
    fi
    if [ ! -f "$matrix_file" ]; then
        echo "Error: matrix file not found: $matrix_file"
        return 1
    fi

    # Output directory for this run
    local timestamp
    timestamp=$(date +"%Y-%m-%d_%H-%M-%S")
    OUTPUT_DIR="$RESULT_DIR/run_$timestamp"
    mkdir -p "$OUTPUT_DIR"

    echo ""
    echo "Running cardinality estimation on all matrices..."

    local index=1
    while IFS= read -r matrix || [ -n "$matrix" ]; do
        if [ -z "$matrix" ]; then
            continue
        fi
        echo "Processing matrix $index..."
        if ! python3 "$card_script" "$matrix" "$OUTPUT_DIR" "$index"; then
            echo "Error: cardinality estimation failed for matrix $index; results were not combined." >&2
            return 1
        fi
        ((index++))
    done < "$matrix_file"

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
    # Machine-readable result path for orchestration scripts
    echo "RNG_OUTPUT_DIR=$OUTPUT_DIR"
}

# --- Non-interactive mode ---
if [ -n "${RNG_ACTION:-}" ]; then
    case "$RNG_ACTION" in
        generate)
            if [ -z "${NUM_VARS:-}" ] || [ -z "${NUM_MATRICES:-}" ]; then
                echo "Error: RNG_ACTION=generate requires NUM_VARS and NUM_MATRICES."
                exit 1
            fi
            generate_matrices "$NUM_VARS" "$NUM_MATRICES"
            exit $?
            ;;
        estimate)
            if [ -z "${CARD_SCRIPT:-}" ] || [ -z "${MATRIX_FILE:-}" ]; then
                echo "Error: RNG_ACTION=estimate requires CARD_SCRIPT and MATRIX_FILE."
                exit 1
            fi
            run_estimation "$CARD_SCRIPT" "$MATRIX_FILE"
            exit $?
            ;;
        *)
            echo "Error: unknown RNG_ACTION '$RNG_ACTION' (use generate or estimate)."
            exit 1
            ;;
    esac
fi

# --- Interactive menu ---
while true; do
    echo ""
    echo "==== RNG MATRIX PIPELINE ===="
    echo "1) Generate matrices"
    echo "2) Run cardinality estimation"
    echo "3) Exit"
    read -r -p "Choose an option: " choice

    if [ "$choice" == "1" ]; then
        read -r -p "Number of variables: " NUM_VARS
        read -r -p "Number of matrices: " NUM_MATRICES

        generate_matrices "$NUM_VARS" "$NUM_MATRICES"

        echo "Done. Returning to menu..."

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

        run_estimation "$CARD_SCRIPT" "$MATRIX_FILE"

    elif [ "$choice" == "3" ]; then
        echo "Exiting..."
        break
    else
        echo "Invalid option."
    fi
done
