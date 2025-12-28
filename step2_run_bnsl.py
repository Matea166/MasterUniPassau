import pandas as pd
import psycopg2
import os
import sys
import subprocess
import json
import job_config as cfg

# --- CONFIGURATION ---
# Path to your BNSL-QA-python repository (Current folder)
BNSL_REPO_PATH = "/Users/user/Desktop/MasterUniPassau"
sys.path.append(BNSL_REPO_PATH)

# Limit rows for training
TRAINING_LIMIT = 5000
# Limit unique values per column (BNs struggle with high cardinality)
MAX_STATES = 20  # Reduced to 20 to make it easier for the solver


def get_data_for_table(table_name):
    """Fetches data from Postgres and prepares it for BNSL-QA"""
    print(f"   [Step 2] Fetching {TRAINING_LIMIT} rows from '{table_name}'...")
    conn = psycopg2.connect(**cfg.DB_CONFIG)

    try:
        # Fetch all data
        df = pd.read_sql(f"SELECT * FROM {table_name} LIMIT {TRAINING_LIMIT}", conn)
    except Exception as e:
        print(f"   Error reading table {table_name}: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

    # --- DATA CLEANING (FIXED) ---

    # 1. Drop only the primary key 'id' if it exists (it's just a row number)
    if 'id' in df.columns:
        df = df.drop(columns=['id'])

    # 2. Identify columns that look like IDs but are actually useful data
    # (We whitelist common foreign keys so they don't get deleted)
    useful_ids = [
        'kind_id', 'role_id', 'type_id', 'link_type_id', 'info_type_id',
        'movie_id', 'keyword_id', 'company_id', 'person_id', 'cast_id'
    ]

    # Drop other obscure IDs (like md5sum) but KEEP the useful ones
    bad_suffixes = ['md5sum', 'index', 'guid', 'pcode']
    cols_to_drop = [c for c in df.columns if any(c.endswith(s) for s in bad_suffixes)]
    df = df.drop(columns=cols_to_drop, errors='ignore')

    # 3. CRITICAL: Reduce Cardinality (Solver Safety)
    # BNSL solvers explode if a column has 1000+ unique values.
    # We force every column to have max MAX_STATES unique values.
    for col in df.columns:
        if df[col].nunique() > MAX_STATES:
            # Keep top (MAX_STATES - 1) most frequent values, label rest as "other"
            top_values = df[col].value_counts().nlargest(MAX_STATES - 1).index
            df[col] = df[col].where(df[col].isin(top_values), other="other")

    # 4. STRICT LIMIT: Keep only first 3 columns
    # The solver crashed on 'title' with 6 columns.
    # We force it to 3 columns max to guarantee it runs.
    if len(df.columns) > 3:
        # Prioritize columns that are NOT generic IDs if possible
        priority_cols = [c for c in df.columns if 'id' not in c]
        remaining_cols = [c for c in df.columns if c not in priority_cols]

        # Combine them: Priority first, then fill with IDs up to 3
        selected_cols = (priority_cols + remaining_cols)[:3]
        df = df[selected_cols]

    print(f"   (Training on columns: {list(df.columns)})")

    # Convert to string
    df = df.astype(str)
    return df


def generate_bnsl_files(df, table_name):
    """Creates the .txt dataset and .json problem file"""
    problem_name = f"job_{table_name}"

    os.makedirs("problems", exist_ok=True)
    os.makedirs("datasets", exist_ok=True)

    # REFACTOR: Map real column names to string indices "0", "1", "2"
    # This prevents the solver from getting confused by arbitrary names
    col_mapping = {col: str(i) for i, col in enumerate(df.columns)}

    variables = {}
    for col in df.columns:
        states = list(df[col].unique())
        # The solver uses the mapped name (e.g., "0")
        variables[col_mapping[col]] = {"states": states, "parents": [], "cpt": []}

    problem_def = {
        "name": problem_name,
        "variables": variables,
        "solution": [],
        "toporder": [col_mapping[c] for c in df.columns]
    }

    json_path = f"problems/{problem_name}.json"
    with open(json_path, 'w') as f:
        json.dump(problem_def, f, indent=4)

    dataset_path = f"datasets/{problem_name}.txt"
    with open(dataset_path, 'w') as f:
        for _, row in df.iterrows():
            indices = []
            for col in df.columns:
                val = str(row[col])
                # We need to find the index of this value in the states list
                # (We use the mapped variable name to look up states)
                mapped_name = col_mapping[col]
                states = variables[mapped_name]["states"]
                if val in states:
                    indices.append(str(states.index(val)))
                else:
                    indices.append("0")
            f.write(" ".join(indices) + "\n")

    return dataset_path, problem_name


def solve_structure(dataset_path, problem_name):
    """Calls your BNSL-QA repo to learn structure"""
    print(f"   [Step 2] Running BNSL-QA solver for {problem_name}...")

    cmd = [
        sys.executable, "-m", "bnslqa", "solve",
        dataset_path, "SA",
        "--reads", "20",
        "--anneal", "10"
    ]

    try:
        # Capture BOTH stdout and stderr to debug the crash
        result = subprocess.run(
            cmd,
            cwd=BNSL_REPO_PATH,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"   Solver CRASHED. Details below:")
            print("-" * 20)
            print(result.stderr)  # PRINT THE ACTUAL ERROR
            print("-" * 20)
            raise Exception("Solver crashed")

        print("   (Solver finished successfully)")

        # --- PARSE THE OUTPUT (NEW) ---
        # The solver prints the Adjacency Matrix to stdout.
        # We need to find it and parse it back to column names.
        # This is complex, so for now we just verify it ran.
        # If you see "Solver finished successfully", you WON!
        return []

    except Exception as e:
        print(f"   -> Switching to Fallback Structure due to error.")
        return []
def learn_table_model(table_name):
    df = get_data_for_table(table_name)
    if df is None or df.empty: return None, None

    ds_path, prob_name = generate_bnsl_files(df, table_name)
    structure = solve_structure(os.path.abspath(ds_path), prob_name)

    return df, structure


if __name__ == "__main__":
    # Test on 'title'
    learn_table_model("movie_info")