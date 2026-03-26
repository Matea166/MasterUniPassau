#!/bin/bash

# Paths
SA_SQA_DIR="../bnsl-qa/dispatch_output/results"
BN_DIR="card_results"

echo "==========================================="
echo "   Card-Estimation Results Merger          "
echo "==========================================="

# 1. Choose SA file
echo -e "\n--- Step 1: Select SA Result File ---"
SA_FILES=($(ls $SA_SQA_DIR/*.csv))
select sa_file in "${SA_FILES[@]}"; do
    [ -n "$sa_file" ] && break
done

# 2. Choose SQA file
echo -e "\n--- Step 2: Select SQA Result File ---"
SQA_FILES=($(ls $SA_SQA_DIR/*.csv))
select sqa_file in "${SQA_FILES[@]}"; do
    [ -n "$sqa_file" ] && break
done

# 3. Choose BN/Postgres file
echo -e "\n--- Step 3: Select BN/Postgres Result File ---"
BN_FILES=($(ls $BN_DIR/*.csv))
select bn_file in "${BN_FILES[@]}"; do
    [ -n "$bn_file" ] && break
done

# 4. Run the Python Merger
python3 merge_csv_logic.py "$sa_file" "$sqa_file" "$bn_file"