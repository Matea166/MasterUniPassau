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

# --- 1. SETUP & STABILITY ---
SEED = 42
np.random.seed(SEED)
random.seed(SEED)
print(f"✅ Random seed set to {SEED} for reproducibility.")

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
OUTPUT_FILE = "results_bnsl_final_verified.csv"

# Configuration
STRUCT_SAMPLE_ROWS = 2000
PARAM_SAMPLE_ROWS = 1000000  # We will fetch this many rows RANDOMLY now
BUCKETS_M = 500
BUCKETS_N = 500
SAFE_PARENT_THRESHOLD = 1000


# --- 3. HELPER: ROBUST PARSING ---
def parse_simple_conditions_robust(wheres_val):
    try:
        cond_list = ast.literal_eval(wheres_val)
        if not isinstance(cond_list, list): return []
        parsed = []
        for cond_str in cond_list:
            if not isinstance(cond_str, str): continue

            # Remove alias prefix (e.g., "n.gender" -> "gender")
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

            if col and val:
                # Normalize Value (Strip Whitespace)
                parsed.append({'col': col, 'val': val.strip()})
        return parsed
    except:
        return []


# --- 4. CORE LOGIC ---

def project_dag_to_safe_tree(dag, df_sample):
    tree = nx.DiGraph()
    tree.add_nodes_from(dag.nodes)
    try:
        order = list(nx.topological_sort(dag))
    except:
        order = list(dag.nodes)
    for node in order:
        parents = list(dag.predecessors(node))
        if parents:
            best_parent = None
            for p in parents:
                if df_sample[p].nunique() <= SAFE_PARENT_THRESHOLD:
                    best_parent = p
                    break
            if best_parent:
                tree.add_edge(best_parent, node)
    return tree


def learn_params_hybrid(structure, df):
    model = nx.DiGraph()
    model.add_nodes_from(structure.nodes)
    model.add_edges_from(structure.edges)

    for node in nx.topological_sort(model):
        # DATA HYGIENE: Convert to string and STRIP whitespace
        raw_series = df[node].fillna('MISSING').astype(str)
        col_data = raw_series.str.strip().tolist()
        n_unique = df[node].nunique()

        # STRATEGY A: EXACT PMF (Low Cardinality)
        if n_unique < 250:
            counts = pd.Series(col_data).value_counts(normalize=True).to_dict()
            model.nodes[node]['type'] = 'exact'
            model.nodes[node]['dist'] = counts
            continue

        # STRATEGY B: HISTOGRAMS (High Cardinality)
        model.nodes[node]['type'] = 'hist'
        parents = list(model.predecessors(node))

        if not parents:
            try:
                h = Histogram(BUCKETS_M, BUCKETS_N)
                h.fit(col_data)
                model.nodes[node]['dist'] = h
            except:
                pass
        else:
            parent = parents[0]
            # Ensure parent data is also clean
            parent_series = df[parent].fillna('MISSING').astype(str)
            parent_data = parent_series.str.strip().tolist()
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

        node_info = model.nodes[col]
        dist_type = node_info.get('type')
        dist = node_info.get('dist')
        if not dist: continue

        p_col = 0.0

        for c in cond_list:
            # Value is already stripped in parser
            val = str(c['val'])
            match_freq = 0.0

            # --- CASE A: EXACT PMF ---
            if dist_type == 'exact':
                match_freq = dist.get(val, 0.0)

                # Numeric fallback
                if match_freq == 0:
                    try:
                        match_freq = dist.get(str(float(val)), 0.0)
                    except:
                        pass

                # Safety Net
                if match_freq == 0: match_freq = 1.0 / total_rows

            # --- CASE B: HISTOGRAMS ---
            elif dist_type == 'hist':
                buckets = []
                if hasattr(dist, 'buckets'):
                    buckets = dist.buckets
                elif hasattr(dist, 'on_hists'):
                    for h in dist.on_hists: buckets.extend(h.buckets)

                for b in buckets:
                    freq = float(b.frequency)
                    left = str(b.left)
                    right = str(b.right)

                    if left == val:
                        match_freq = freq
                        break

                    try:
                        if abs(float(left) - float(val)) < 0.0001:
                            match_freq = freq
                            break
                    except:
                        pass

                    in_range = False
                    try:
                        if float(left) <= float(val) <= float(right): in_range = True
                    except:
                        if left <= val <= right: in_range = True

                    if in_range:
                        try:
                            width = float(right) - float(left)
                            if width > 0:
                                match_freq = max(match_freq, freq / width)
                            else:
                                match_freq = max(match_freq, freq)
                        except:
                            match_freq = max(match_freq, freq * 0.05)

                if match_freq == 0:
                    match_freq = 1.0 / total_rows

            p_col = match_freq

        p_total *= p_col

    return p_total


# --- 5. MAIN ---
def main():
    print("--- STARTING BNSL-SA VERIFIED SOLUTION (RANDOM SAMPLING) ---")

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

            # 1. Get total rows
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            table_counts[table] = count

            # 2. Structure Learning (Small Sample - Head is fine)
            struct_data = pd.read_sql(text(f"SELECT * FROM {table} LIMIT {STRUCT_SAMPLE_ROWS}"), conn)

            # 3. Parameter Learning (Large RANDOM Sample)
            # Use TABLESAMPLE BERNOULLI for true randomness avoiding clustering bias
            if count <= PARAM_SAMPLE_ROWS:
                param_query = f"SELECT * FROM {table}"
            else:
                # Calculate percentage needed to get ~PARAM_SAMPLE_ROWS
                pct = (PARAM_SAMPLE_ROWS / count) * 100
                # Add 10% buffer to be safe, cap at 100
                pct = min(pct * 1.1, 100.0)
                # BERNOULLI scans the whole table but picks rows randomly.
                # This fixes the "All Males" bug.
                param_query = f"SELECT * FROM {table} TABLESAMPLE BERNOULLI({pct}) LIMIT {PARAM_SAMPLE_ROWS}"

            param_data = pd.read_sql(text(param_query), conn)

            conn.close()

            # --- BNSL LOGIC ---
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

            # Params (Hybrid Verified)
            tree = project_dag_to_safe_tree(structure, struct_data)

            # Clean Parameter Data IN PLACE
            clean_param = param_data.copy()
            for c in clean_param.columns:
                if clean_param[c].dtype == 'object':
                    clean_param[c] = clean_param[c].fillna('MISSING')
                else:
                    clean_param[c] = clean_param[c].fillna(0)

            model = learn_params_hybrid(tree, clean_param)
            models[table] = model

        except Exception as e:
            # print(f"Error {table}: {e}")
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
    print(f"BNSL-SA Verified Q-Error: {df['q_bn'].mean():.2f}")
    print("=" * 40)

    # BREAKDOWN
    print("\nError Breakdown by Table:")
    print(df.groupby('table')['q_bn'].mean().sort_values(ascending=False))

    df.to_csv(OUTPUT_FILE, index=False)


if __name__ == "__main__":
    main()