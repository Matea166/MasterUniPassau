#!/usr/bin/env bash
# Paths
SA_SQA_DIR="../bnsl-qa/dispatch_output/results"
BN_DIR="card_results"
RNG_MATRIX_DIR="../bnsl-qa/RNG_Matrix/results"

echo "==========================================="
echo "   Card-Estimation Results Merger          "
echo "==========================================="

# 1. Choose SA file
echo -e "\n--- Step 1: Select SA Result File ---"
mapfile -t SA_FILES < <(find "$SA_SQA_DIR" -maxdepth 1 -type f -name "*SA*.csv")
if [ ${#SA_FILES[@]} -eq 0 ]; then
    echo "No SA files found in $SA_SQA_DIR"
    exit 1
fi
select sa_file in "${SA_FILES[@]}"; do
    [ -n "$sa_file" ] && break
done

# 2. Choose SQA file
echo -e "\n--- Step 2: Select SQA Result File ---"
mapfile -t SQA_FILES < <(find "$SA_SQA_DIR" -maxdepth 1 -type f -name "*SQA*.csv")
select sqa_file in "${SQA_FILES[@]}"; do
    [ -n "$sqa_file" ] && break
done

# 3. Choose BN/Postgres file
echo -e "\n--- Step 3: Select bnsl Result File ---"
BN_FILES=($(ls $BN_DIR/*.csv 2>/dev/null))
select bn_file in "${BN_FILES[@]}"; do
    [ -n "$bn_file" ] && break
done

# 4. Choose RNG Matrix file
echo -e "\n--- Step 4: Add RNG Matrix results? (y/n) ---"
read -r add_rng
rng_file="NONE"

if [[ "$add_rng" == "y" ]]; then
    echo "Searching for RNG run folders in $RNG_MATRIX_DIR..."

    # Try the specific path first, then try a broader search in the parent dir if it fails
    mapfile -t rng_files < <(find "$RNG_MATRIX_DIR" -type f -name "final_cardinality.csv" 2>/dev/null)

    if [ ${#rng_files[@]} -eq 0 ]; then
        echo "Direct path failed. Trying broader search in ../bnsl-qa/ ..."
        mapfile -t rng_files < <(find "../bnsl-qa" -path "*/RNG_Matrix/*" -name "final_cardinality.csv" 2>/dev/null)
    fi

    if [ ${#rng_files[@]} -eq 0 ]; then
        echo "Still no RNG files found. Please check if the folder exists in ../bnsl-qa/"
    else
        echo "Select which RNG run to use:"
        select selected_rng in "${rng_files[@]}"; do
            if [[ -n "$selected_rng" ]]; then
                rng_file="$selected_rng"
                break
            else
                echo "Invalid selection"
            fi
        done
    fi
fi

# 5. Run the Python Merger
python3 merge_csv_logic.py "$sa_file" "$sqa_file" "$bn_file" "$rng_file"
