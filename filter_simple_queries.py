import pandas as pd
import ast
import os

INPUT_FILE = "results_single_relation_final.csv"
OUTPUT_FILE = "results_simple_queries.csv"


def is_simple_query(wheres_str):
    """
    Returns True ONLY if the query uses simple equality '='.
    Rejects: LIKE, BETWEEN, IN, >, <, >=, <=
    """
    try:
        # The 'wheres' column is a string representation of a list
        conds = ast.literal_eval(wheres_str)

        if not isinstance(conds, list) or len(conds) == 0:
            return False

        for cond in conds:
            if not isinstance(cond, str):
                return False

            cond_upper = cond.upper()

            # 1. REJECT Complex Operators
            if "LIKE" in cond_upper: return False
            if "BETWEEN" in cond_upper: return False
            if " IN " in cond_upper or cond_upper.startswith("IN "): return False

            # 2. REJECT Inequalities
            # We look for > or <.
            # Note: This might catch arrows '->' in some weird text, but standard SQL is safe.
            if ">" in cond or "<" in cond:
                return False

            # 3. MUST HAVE Equality
            if "=" not in cond:
                return False

        return True
    except:
        return False


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        return

    print(f"Reading {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE)
    print(f"Original Row Count: {len(df)}")

    # Apply Filter
    df['is_simple'] = df['wheres'].apply(is_simple_query)
    df_simple = df[df['is_simple']].copy()

    # Drop the helper column
    df_simple.drop(columns=['is_simple'], inplace=True)

    print(f"Filtered Row Count: {len(df_simple)}")

    if len(df_simple) > 0:
        df_simple.to_csv(OUTPUT_FILE, index=False)
        print(f"\n✅ Success! Saved {len(df_simple)} simple queries to: {OUTPUT_FILE}")
        print("You can now run the BNSL-SA estimation script using this new file.")

        # Preview
        print("\nPreview of Simple Queries:")
        print(df_simple[['table', 'wheres'] if 'table' in df_simple.columns else 'wheres'].head().to_string())
    else:
        print("❌ Warning: No queries met the 'Simple' criteria.")


if __name__ == "__main__":
    main()