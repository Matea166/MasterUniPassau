import pandas as pd
import numpy as np
import sqlalchemy
from sqlalchemy import text
import ast
import sys
import os
import tqdm
import re
import networkx as nx
import subprocess
import json
import tempfile
import random
from sklearn.preprocessing import LabelEncoder

# --- 1. SETUP ---
sys.path.append(os.getcwd())

try:
    from phd import bn, rel

    try:
        from phd.histogram import Histogram
        from phd.cpd import CPD
    except ImportError:
        Histogram = getattr(bn, 'Histogram', None)
        CPD = getattr(bn, 'CPD', None)
    print("✅ Imported 'phd' (TLDKS).")
except ImportError:
    print("❌ Error: 'phd' folder not found.")
    sys.exit(1)

# --- 2. CONFIGURATION ---
DB_URI = "postgresql://postgres:postgres@localhost:5433/job"
INPUT_FILE = "results_simple_queries.csv"
OUTPUT_FILE = "results_bnsl_tuned.csv"

# Hyperparameters
STRUCT_SAMPLE_ROWS = 2000
PARAM_SAMPLE_ROWS = 1000000
# Increased buckets to better handle high-cardinality columns like 'name'
BUCKETS_M = 500
BUCKETS_N = 500


# --- 3. HELPER: PARSING ---
def parse_simple_conditions_robust(wheres_val):
    try:
        cond_list = ast.literal_eval(wheres_val)
        if not isinstance(cond_list, list): return []
        parsed = []
        for cond_str in cond_list:
            if not isinstance(cond_str, str): continue
            if "." in cond_str:
                clean = cond_str.split(".", 1)[1]
            else:
                clean = cond_str

            m_quote = re.search(r"(\w+)\s*=\s*'(.+)'", clean)
            m_num = re.search(r"(\w+)\s*=\s*([0-9\.]+)", clean)

            col, val = None, None
            if m_quote:
                col = m_quote.group(1)
                val = m_quote.group(2).replace("''", "'")
            elif m_num:
                col = m_num.group(1)
                val = m_num.group(2)

            if col and val: parsed.append({'col': col, 'val': val})
        return parsed
    except:
        return []


# --- 4. CORE LOGIC ---

def project_dag_to_tree(dag):
    tree = nx.DiGraph()
    tree.add_nodes_from(dag.nodes)
    try:
        order = list(nx.topological_sort(dag))
    except:
        order = list(dag.nodes)
    for node in order:
        parents = list(dag.predecessors(node))
        if parents:
            tree.add_edge(parents[0], node)
    return tree


def learn_params_tldks(structure, df):
    model = nx.DiGraph()
    model.add_nodes_from(structure.nodes)
    model.add_edges_from(structure.edges)

    for node in nx.topological_sort(model):
        parents = list(model.predecessors(node))
        col_data = df[node].tolist()

        if not parents:
            try:
                h = Histogram(BUCKETS_M, BUCKETS_N)
                h.fit(col_data)
                model.nodes[node]['dist'] = h
            except:
                pass
        else:
            parent = parents[0]
            parent_data = df[parent].tolist()
            try:
                cpd = CPD(BUCKETS_M, BUCKETS_N, BUCKETS_M, BUCKETS_N)
                cpd.fit(parent_data, col_data)
                model.nodes[node]['dist'] = cpd
            except:
                pass
    return model


def calculate_prob(model, conds, total_rows):
    p_total = 1.0

    col_conds = {}
    for c in conds:
        col = c['col']
        if col not in col_conds: col_conds[col] = []
        col_conds[col].append(c)

    for col, cond_list in col_conds.items():
        if col not in model.nodes: continue

        dist = model.nodes[col].get('dist')
        if not dist: continue

        buckets = []
        if hasattr(dist, 'buckets'):
            buckets = dist.buckets
        elif hasattr(dist, 'on_hists'):
            for h in dist.on_hists: buckets.extend(h.buckets)

        p_col = 0.0

        for c in cond_list:
            val = str(c['val'])
            match_freq = 0.0

            for b in buckets:
                freq = float(b.frequency)
                left = str(b.left)
                right = str(b.right)

                # Check Numeric vs String nature
                is_numeric_bucket = False
                try:
                    nl, nr = float(left), float(right)
                    is_numeric_bucket = True
                except:
                    pass

                # 1. Exact Match (MCV)
                is_exact = False
                if left == val:
                    is_exact = True
                elif is_numeric_bucket:
                    try:
                        if abs(float(left) - float(val)) < 0.0001: is_exact = True
                    except:
                        pass

                if is_exact:
                    match_freq = freq
                    break

                    # 2. Range Containment
                in_range = False
                try:
                    if is_numeric_bucket:
                        if float(left) <= float(val) <= float(right): in_range = True
                    else:
                        if left <= val <= right: in_range = True
                except:
                    pass

                if in_range:
                    # CRITICAL FIX: Differentiate behavior
                    if is_numeric_bucket:
                        # Numeric: Density makes sense (e.g. Year)
                        width = float(right) - float(left)
                        if width > 0:
                            match_freq = max(match_freq, freq / width)
                        else:
                            match_freq = max(match_freq, freq)
                    else:
                        # String: DO NOT guess density for Equality Queries.
                        # If it's a string range bucket and NOT an exact match,
                        # the value is likely rare or missing.
                        # We do NOT add probability here. We let it fall through to the safety floor.
                        # This prevents "Zimmer" from getting 10% of "Z" bucket.
                        pass

                        # Safety Floor / Rare Item Probability
            if match_freq == 0:
                if total_rows > 0:
                    # Assume at least 1 row (or 0.5 for under-estimation safety)
                    match_freq = 1.0 / total_rows
                else:
                    match_freq = 0.000001

            p_col = match_freq

        p_total *= p_col

    return p_total


# --- 5. MAIN ---
def main():
    print("--- STARTING BNSL-SA TUNED (Strict Equality) ---")

    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        return
    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df)} simple queries.")

    engine = sqlalchemy.create_engine(DB_URI)

    def get_tab(x):
        try:
            return ast.literal_eval(x)[0] if isinstance(ast.literal_eval(x), (list, tuple)) else str(
                ast.literal_eval(x))
        except:
            return x

    df['table'] = df['relations'].apply(get_tab)
    unique_tables = df['table'].unique()

    models = {}
    table_counts = {}

    print(f"\nProcessing {len(unique_tables)} tables...")

    for table in tqdm.tqdm(unique_tables):
        try:
            conn = engine.connect()
            table_counts[table] = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()

            struct_data = pd.read_sql(text(f"SELECT * FROM {table} LIMIT {STRUCT_SAMPLE_ROWS}"), conn)
            param_data = pd.read_sql(text(f"SELECT * FROM {table} LIMIT {PARAM_SAMPLE_ROWS}"), conn)
            conn.close()

            # SA Structure
            bnsl_data = struct_data.copy()
            for c in bnsl_data.columns:
                if bnsl_data[c].dtype == 'object':
                    bnsl_data[c] = bnsl_data[c].fillna('MISSING')
                else:
                    bnsl_data[c] = bnsl_data[c].fillna(0)
                bnsl_data[c] = LabelEncoder().fit_transform(bnsl_data[c].astype(str))

            with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tmp:
                bnsl_data.to_csv(tmp.name, sep=' ', index=False, header=False)
                tmp_path = tmp.name

            # Note: We keep reads low for speed, 20 is usually fine for single-table
            cmd = [sys.executable, "-m", "bnslqa", "solve", tmp_path, "SA", "--reads", "20"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            os.remove(tmp_path)

            structure = nx.DiGraph()
            structure.add_nodes_from(struct_data.columns)

            if result.returncode == 0:
                try:
                    out = result.stdout
                    s = out.find('{');
                    e = out.rfind('}') + 1
                    sol = json.loads(out[s:e])
                    matrix = sol.get('solution', [])
                    cols = list(struct_data.columns)
                    for i, r in enumerate(matrix):
                        for j, v in enumerate(r):
                            if v == 1: structure.add_edge(cols[i], cols[j])
                except:
                    pass

            # Params (High Buckets)
            tree = project_dag_to_tree(structure)
            clean_param = param_data.copy()
            for c in clean_param.columns:
                if clean_param[c].dtype == 'object':
                    clean_param[c] = clean_param[c].fillna('MISSING')
                else:
                    clean_param[c] = clean_param[c].fillna(0)

            model = learn_params_tldks(tree, clean_param)
            models[table] = model

        except Exception as e:
            pass

    # ESTIMATE
    print("\nEstimating...")
    estimates = []

    for idx, row in df.iterrows():
        table = row['table']
        model = models.get(table)
        total_rows = table_counts.get(table, 1000)

        if model:
            conds = parse_simple_conditions_robust(row['wheres'])
            if conds:
                prob = calculate_prob(model, conds, total_rows)
            else:
                prob = 1.0

            est = prob * total_rows
            if est < 1: est = 1
        else:
            est = row['postgres_estimate']

        estimates.append(int(est))

    df['bn_estimate'] = estimates

    def q_error(est, true):
        if est <= 0: est = 1
        if true <= 0: true = 1
        return max(est / true, true / est)

    df['q_pg'] = df.apply(lambda x: q_error(x['postgres_estimate'], x['true_cardinality']), axis=1)
    df['q_bn'] = df.apply(lambda x: q_error(x['bn_estimate'], x['true_cardinality']), axis=1)

    print("\n" + "=" * 40)
    print(f"Subset: {len(df)} Simple Queries")
    print(f"Postgres Mean Q-Error: {df['q_pg'].mean():.2f}")
    print(f"BNSL-SA Tuned Q-Error: {df['q_bn'].mean():.2f}")
    print("=" * 40)

    # BREAKDOWN
    print("\nError Breakdown by Table:")
    print(df.groupby('table')['q_bn'].mean().sort_values(ascending=False))

    df.to_csv(OUTPUT_FILE, index=False)


if __name__ == "__main__":
    main()