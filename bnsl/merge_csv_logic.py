import pandas as pd
import sys
import re
import matplotlib.pyplot as plt
import numpy as np

if len(sys.argv) < 4:
    print("Usage: python3 merge_csv_logic.py <sa_path> <sqa_path> <bn_path>")
    sys.exit(1)

sa_path, sqa_path, bn_path = sys.argv[1], sys.argv[2], sys.argv[3]

# ==========================================
# 1. LOAD AND NORMALIZE
# ==========================================
df_sa = pd.read_csv(sa_path)
df_sqa = pd.read_csv(sqa_path)
df_bn = pd.read_csv(bn_path)


def normalize_query(q):
    if not isinstance(q, str): return q

    # 1. Extract ONLY the part after WHERE
    match = re.search(r'WHERE\s+(.*)', q, re.IGNORECASE)
    key = match.group(1) if match else q

    # 2. Convert to lowercase and remove spaces/semicolons
    key = key.lower()
    key = "".join(key.split()).replace(";", "")

    # 3. Remove all quotes
    key = key.replace("'", "").replace('"', "")

    # 4. Normalize numbers (change 2.0 to 2, 30.0 to 30)
    key = key.replace(".0", "")

    return key


df_sa['join_key'] = df_sa['query_sql'].apply(normalize_query)
df_sqa['join_key'] = df_sqa['query_sql'].apply(normalize_query)
df_bn['join_key'] = df_bn['query_sql'].apply(normalize_query)

# --- DEBUG SECTION ---
print("\n--- Join Key Debug ---")
if not df_sa.empty: print(f"SA Key Sample: {df_sa['join_key'].iloc[0]}")
if not df_bn.empty: print(f"BN Key Sample: {df_bn['join_key'].iloc[0]}")


# ---------------------

# ==========================================
# 2. MERGE DATA
# ==========================================

# Create helper for Graph column formatting
def format_graph_cols(df):
    cols = [c for c in df.columns if 'Graph' in c or '.png' in c]
    if not cols: return pd.Series(["No Graph Data"] * len(df))
    return df.apply(lambda row: " | ".join([f"{c.split('.')[0]}: {row[c]}" for c in cols]), axis=1)


# Initialize final_output
final_output = pd.DataFrame({
    'query': df_sa['query_sql'],
    'join_key': df_sa['join_key'],
    'SA_str': format_graph_cols(df_sa),
    'SQA_str': format_graph_cols(df_sqa)
})

# Select BN columns
df_bn_subset = df_bn[['join_key', 'bn_est_cardinality', 'true_cardinality', 'pg_est_cardinality']]

# Perform Merge
merged = pd.merge(final_output, df_bn_subset, on='join_key', how='left')


# Helper to get graph data for plotting
def get_graph_data(df, prefix):
    cols = [c for c in df.columns if 'Graph' in c or '.png' in c]
    data = df[cols].copy()
    data.columns = [f"{prefix}_{c.split('.')[0]}" for c in data.columns]
    return data


sa_graphs = get_graph_data(df_sa, "SA")
sqa_graphs = get_graph_data(df_sqa, "SQA")

# Combine for plotting
plot_df = pd.concat([merged, sa_graphs, sqa_graphs], axis=1)

# Save the final consolidated CSV
final_csv_df = pd.DataFrame({
    'query': merged['query'],
    'SA': merged['SA_str'],
    'SQA': merged['SQA_str'],
    'BNSL': merged['bn_est_cardinality'],
    'true': merged['true_cardinality'],
    'postgres_est': merged['pg_est_cardinality']
})

timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
output_base = f"combined_results_{timestamp}"
final_csv_df.to_csv(f"{output_base}.csv", index=False)
print(f"CSV saved: {output_base}.csv")

# ==========================================
# 3. VISUALIZATION
# ==========================================
print("Generating high-contrast separated visualization...")

# Identify columns for the plot
sa_cols = [c for c in plot_df.columns if c.startswith('SA_Graph')]
sqa_cols = [c for c in plot_df.columns if c.startswith('SQA_Graph')]
bn_col = 'bn_est_cardinality'
pg_col = 'pg_est_cardinality'
true_col = 'true_cardinality'

# Logic for grouping bars if more than 4
group_sa = len(sa_cols) > 4
group_sqa = len(sqa_cols) > 4

# Adjust bar count for width calculation
n_sa_plot = 1 if group_sa else len(sa_cols)
n_sqa_plot = 1 if group_sqa else len(sqa_cols)
num_estimators = 3 + n_sa_plot + n_sqa_plot

labels = [f"Q{i + 1}" for i in range(len(plot_df))]
x = np.arange(len(labels))
total_group_width = 0.8
bar_gap = 0.02
bar_width = (total_group_width - (bar_gap * (num_estimators - 1))) / num_estimators

fig, ax = plt.subplots(figsize=(22, 10))


# --- HELPER FUNCTION TO ADD NUMBERS ON TOP OF BARS ---
def add_bar_labels(rects, extra_info=None):
    for i, rect in enumerate(rects):
        height = rect.get_height()
        if height >= 0:
            label = f'{height:.1f}' if extra_info is None else extra_info[i]
            ax.annotate(label,
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 5),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=8, rotation=45)


current_pos = x - (total_group_width / 2) + (bar_width / 2)

# Plot True
r_true = ax.bar(current_pos, plot_df[true_col].fillna(0), bar_width, label='True', color='#27ae60')
add_bar_labels(r_true)
current_pos += (bar_width + bar_gap)

# Plot SA
if group_sa:
    data_sa = plot_df[sa_cols]  # removed .fillna(0)
    avgs = data_sa.mean(axis=1, skipna=True).round(1)
    sems = data_sa.sem(axis=1, skipna=True).round(1)
    mins = data_sa.min(axis=1).round(1)
    maxs = data_sa.max(axis=1).round(1)

    r_sa = ax.bar(current_pos, avgs, bar_width, yerr=sems, label='SA (AVG + SEM)', color='#2980b9', capsize=4)
    info = [f"Avg:{a:.1f}\nRange:[{m:.1f}-{x:.1f}]" for a, m, x in zip(avgs, mins, maxs)]
    add_bar_labels(r_sa, extra_info=info)
    current_pos += (bar_width + bar_gap)
else:
    for col in sa_cols:
        r_sa = ax.bar(current_pos, plot_df[col].fillna(0), bar_width, label=col, color='#2980b9')
        add_bar_labels(r_sa)
        current_pos += (bar_width + bar_gap)

# Plot SQA
if group_sqa:
    data_sqa = plot_df[sqa_cols]  # removed .fillna(0)
    avgs = data_sqa.mean(axis=1, skipna=True).round(1)
    sems = data_sqa.sem(axis=1, skipna=True).round(1)
    mins = data_sqa.min(axis=1).round(1)
    maxs = data_sqa.max(axis=1).round(1)

    r_sqa = ax.bar(current_pos, avgs, bar_width, yerr=sems, label='SQA (AVG + SEM)', color='#8e44ad', capsize=4)
    info = [f"Avg:{a:.1f}\nRange:[{m:.1f}-{x:.1f}]" for a, m, x in zip(avgs, mins, maxs)]
    add_bar_labels(r_sqa, extra_info=info)
    current_pos += (bar_width + bar_gap)
else:
    for col in sqa_cols:
        r_sqa = ax.bar(current_pos, plot_df[col].fillna(0), bar_width, label=col, color='#8e44ad')
        add_bar_labels(r_sqa)
        current_pos += (bar_width + bar_gap)

# Plot BN & PG
r_bn = ax.bar(current_pos, plot_df[bn_col].fillna(0), bar_width, label='BNSL', color='#e67e22')
add_bar_labels(r_bn)
current_pos += (bar_width + bar_gap)

r_pg = ax.bar(current_pos, plot_df[pg_col].fillna(0), bar_width, label='Postgres', color='#7f8c8d')
add_bar_labels(r_pg)

ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.legend()
ax.margins(y=0.2)

plt.savefig(f"{output_base}.png", dpi=300)
print(f"Final polished histogram saved: {output_base}.png")