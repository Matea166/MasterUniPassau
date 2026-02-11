import pandas as pd
import operator
import os
import graphviz
from bnsl.tldks_2020.bn import BayesianNetwork
from bnsl.tldks_2020.rel import Relation

# ==========================================
# 1. CONFIGURATION
# ==========================================
CSV_FILE = "NHANES_age_prediction"
DATA_PATH = f"bn/data/{CSV_FILE}.csv"
OUTPUT_DIR = "../graphs"
RANDOM_STATE = 42

# Using ALL features
KEEP_COLUMNS = [
    'age_group',
    'RIDAGEYR',
    'RIAGENDR',
    'PAQ605',
    'BMXBMI',
    'LBXGLU',
    'DIQ010',
    'LBXGLT',
    'LBXIN'
]

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# 2. DATA LOADING & PREPROCESSING
# ==========================================
print(f"--- 1. Loading Data from {DATA_PATH} ---")

if not os.path.exists(DATA_PATH):
    print(f"ERROR: File not found at {DATA_PATH}.")
    exit(1)

# Load Full Dataset
df = pd.read_csv(DATA_PATH, low_memory=False, escapechar='\\')
total_rows_true = len(df)
print(f"Original Row Count: {total_rows_true}")

# --- FEATURE SELECTION ---
print(f"Filtering to {len(KEEP_COLUMNS)} features...")
available_cols = [c for c in KEEP_COLUMNS if c in df.columns]
missing_cols = set(KEEP_COLUMNS) - set(available_cols)
if missing_cols:
    print(f"Warning: Missing columns: {missing_cols}")
df = df[available_cols]

# --- CLEANING ---
# 1. Fill Missing Values
df = df.fillna('MISSING')

# 2. Convert all to String (Discrete BN requirement)
for col in df.columns:
    df[col] = df[col].astype(str)

# ==========================================
# 3. TRAINING (FULL DATASET)
# ==========================================
print("\n--- 2. Training Bayesian Network (Full Data) ---")
print(f"Training on {len(df)} rows.")

# Create Relation from the FULL dataframe
relation = Relation(df)

# Structure Learning (Chow-Liu)
bn = BayesianNetwork().fit(relation)

# Parameter Learning (Histograms/CPDs)
bn.update(relation)
print("Training Complete.")

# ==========================================
# 4. GENERATE GRAPH
# ==========================================
print("\n--- 3. Generating Graph ---")
try:
    dot_file = os.path.join(OUTPUT_DIR, f"{CSV_FILE}_bn.dot")
    png_file = os.path.join(OUTPUT_DIR, f"{CSV_FILE}_bn.png")
    
    with open(dot_file, "w") as f:
        f.write(str(bn.to_dot()))
    
    graphviz.render("dot", "png", dot_file, outfile=png_file)
    print(f"[Graph] Saved to: {png_file}")
except Exception as e:
    print(f"[Graph] Warning: Graphviz failed. {e}")

# ==========================================
# 5. ROBUST ESTIMATION ENGINE
# ==========================================

def op_like(val, pattern):
    val = str(val)
    pattern = str(pattern)
    if pattern.startswith('%') and pattern.endswith('%'): return pattern[1:-1] in val
    elif pattern.endswith('%'): return val.startswith(pattern[:-1])
    elif pattern.startswith('%'): return val.endswith(pattern[1:])
    return val == pattern

OPS = {
    '>': operator.gt, '<': operator.lt, '>=': operator.ge, '<=': operator.le,
    '==': operator.eq, '=': operator.eq, '!=': operator.ne,
    'LIKE': op_like, 'IS_NOT': operator.ne 
}

def parse_val_robust(val_str):
    try:
        return float(val_str)
    except ValueError:
        return str(val_str)

def get_bn_domain(bn, attribute):
    if attribute not in bn.nodes:
        raise ValueError(f"Attribute '{attribute}' not found in BN")
    dist = bn.nodes[attribute]['dist']
    domain = set()
    def extract_buckets(obj):
        if hasattr(obj, 'buckets'):
            for b in obj.buckets:
                domain.add(b.left); domain.add(b.right)
        elif hasattr(obj, 'on_hists'):
            for h in obj.on_hists: extract_buckets(h)
            if hasattr(obj, 'on_null_hist') and obj.on_null_hist: extract_buckets(obj.on_null_hist)
    extract_buckets(dist)
    if hasattr(dist, 'keys'): domain.update(dist.keys())
    return list(domain)

def estimate_cardinality(bn, total_rows, query_id, filters):
    print(f"\n" + "="*60)
    print(f"QUERY [{query_id}]")
    print(f"Logic: {filters}")
    print("-" * 60)
    
    involved_cols = list(set([f['col'] for f in filters]))
    
    if len(involved_cols) == 1:
        col = involved_cols[0]
        try:
            domain = get_bn_domain(bn, col)
        except Exception as e:
            print(f"Error accessing BN domain: {e}"); return
            
        valid_prob_sum = 0.0
        contributing_values = []

        for val_str in domain:
            val_parsed = parse_val_robust(val_str)
            if val_parsed is None: continue

            match = True
            for f in filters:
                op_func = OPS[f['op']]
                threshold = f['val']
                try:
                    if not op_func(val_parsed, threshold):
                        match = False; break
                except TypeError:
                    match = False; break
            
            if match:
                try:
                    prob = bn.p(**{col: val_str})
                    if prob > 0:
                        valid_prob_sum += prob
                        contributing_values.append((val_str, prob))
                except: pass

        contributing_values.sort(key=lambda x: x[1], reverse=True)
        print(f"Status: Scanned {len(domain)} known values in BN for '{col}'.")
        print(f"Matches: Found {len(contributing_values)} valid values.")
        
        if len(contributing_values) > 0:
            print("\n--- PROBABILITIES USED (Top 3) ---")
            for v, p in contributing_values[:3]:
                print(f"   Val: '{v}'  |  Prob: {p:.6f}")
        else:
            print("\n[!] No direct matches found in BN memory.")

        est_rows = valid_prob_sum * total_rows
        print("-" * 30)
        print(f"Total Probability: {valid_prob_sum:.6f}")
        print(f"Estimated Cardinality: {int(est_rows)}")
        print("="*60)
        return est_rows

    else:
        print("Note: Multi-column queries require Joint Inference.")
        return 0

# ==========================================
# 6. EXECUTE QUERIES
# ==========================================

queries = [

    # ID = Id for the query, Filters = List of conditions (col, operator, value)
    # col = Column to filter on, op = Operator (>, <, =, !=), val = Value to compare against


    # Q1: High Insulin (LBXIN > 20)
    {'id': 'Q1_HighInsulin', 'filters': [{'col': 'LBXIN', 'op': '>', 'val': 20.0}]},
    
    # Q2: Diabetic (DIQ010 = 1)
    {'id': 'Q2_Diabetic', 'filters': [{'col': 'DIQ010', 'op': '=', 'val': 1.0}]},
    
    # Q3: Active People (PAQ605 = 1)
    {'id': 'Q3_Active', 'filters': [{'col': 'PAQ605', 'op': '=', 'val': 1.0}]},
    
    # Q4: High Glucose (LBXGLU > 120)
    {'id': 'Q4_HighGlucose', 'filters': [{'col': 'LBXGLU', 'op': '>', 'val': 120.0}]},
    
    # Q5: Seniors (Target)
    {'id': 'Q5_Senior', 'filters': [{'col': 'age_group', 'op': '=', 'val': 'Senior'}]},
]

print(f"\nStarting Execution of {len(queries)} Queries...")

for q in queries:
    estimate_cardinality(bn, total_rows_true, q['id'], q['filters'])

print("\nProcessing Complete.")