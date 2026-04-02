#!/opt/homebrew/bin/bash

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
    read -p "Choose an option: " choice

    # ----------------------------
    # OPTION 1: GENERATE MATRICES
    # ----------------------------
    if [ "$choice" == "1" ]; then
        read -p "Number of variables: " NUM_VARS
        read -p "Number of matrices: " NUM_MATRICES

        echo "Generating matrices..."
        python3 generate_RNG_matrices.py "$NUM_VARS" "$NUM_MATRICES" "$MATRIX_DIR"

        echo "Done. Returning to menu..."

    # ----------------------------
    # OPTION 2: RUN CARDINALITY
    # ----------------------------
    elif [ "$choice" == "2" ]; then

        echo ""
        echo "Select a cardinality estimation script:"

        files=(cardinality_estimation/cardinality_estimation_*.py)

        if [ ${#files[@]} -eq 0 ]; then
            echo "No cardinality_estimation_*.py files found."
            continue
        fi

        for i in "${!files[@]}"; do
            echo "$((i+1))) ${files[$i]}"
        done

        read -p "Option: " file_choice
        CARD_SCRIPT=${files[$((file_choice-1))]}

        # ----------------------------
        # SELECT MATRIX FILE
        # ----------------------------
        echo ""
        echo "Select a matrix file:"

        matrices_files=($MATRIX_DIR/*.txt)

        if [ ${#matrices_files[@]} -eq 0 ]; then
            echo "No matrix files found."
            continue
        fi

        for i in "${!matrices_files[@]}"; do
            echo "$((i+1))) $(basename "${matrices_files[$i]}")"
        done

        read -p "Option: " matrix_choice
        MATRIX_FILE=${matrices_files[$((matrix_choice-1))]}

        # ----------------------------
        # CREATE OUTPUT DIR
        # ----------------------------
        TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
        OUTPUT_DIR="$RESULT_DIR/run_$TIMESTAMP"
        mkdir -p "$OUTPUT_DIR"

        echo ""
        echo "Running cardinality estimation on all matrices..."

        # ----------------------------
        # READ MATRICES AND PROCESS
        # ----------------------------
        mapfile -t matrices < "$MATRIX_FILE"

        index=1

        # Read the file line by line, ignoring empty lines
        while IFS= read -r matrix || [ -n "$matrix" ]; do
            if [ -z "$matrix" ]; then
                continue
            fi

            echo "Processing matrix $index..."

            # Pass ONE matrix string at a time
            python3 "$CARD_SCRIPT" "$matrix" "$OUTPUT_DIR" "$index"

            ((index++))
        done < "$MATRIX_FILE"

        echo ""
        echo "All matrices processed."

        # ----------------------------
        # COMBINE CSV FILES
        # ----------------------------
        echo "Combining all CSV results into one file..."

        python3 <<EOF
import glob
import pandas as pd
import os

output_dir = "$OUTPUT_DIR"
final_csv = os.path.join(output_dir, "final_cardinality.csv")

csv_files = sorted(glob.glob(os.path.join(output_dir, "graph_*_cardinality.csv")))

if not csv_files:
    print("No CSV files found to combine.")
    exit()

# Load first CSV
df_final = pd.read_csv(csv_files[0])
first_name = os.path.basename(csv_files[0]).replace("_cardinality.csv", "")
df_final = df_final.rename(columns={"estimated_cardinality": first_name})

# Merge remaining CSVs
for csv in csv_files[1:]:
    df = pd.read_csv(csv)
    name = os.path.basename(csv).replace("_cardinality.csv", "")
    df_final[name] = df["estimated_cardinality"]

df_final.to_csv(final_csv, index=False)

print(f"Final CSV saved at: {final_csv}")
EOF

        echo "Results saved in: $OUTPUT_DIR"

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