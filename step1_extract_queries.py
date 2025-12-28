import os
import re
import json
import job_config as cfg


def run():
    print(f"--- [Step 1] Scanning queries in {cfg.QUERIES_PATH} ---")

    # Regex to capture: alias.column operator 'value'
    # Example: t.production_year > 2010
    pattern = re.compile(r"\b([a-z0-9_]+)\.([a-z0-9_]+)\s*(=|>|<|>=|<=|LIKE)\s*('?[^'\n\s\)]+'?)", re.IGNORECASE)

    all_predicates = []

    if not os.path.exists(cfg.QUERIES_PATH):
        print(f"ERROR: Could not find queries at {cfg.QUERIES_PATH}")
        return

    for filename in os.listdir(cfg.QUERIES_PATH):
        if not filename.endswith(".sql"): continue

        with open(os.path.join(cfg.QUERIES_PATH, filename), 'r') as f:
            content = f.read()
            matches = pattern.findall(content)

            for alias, col, op, val in matches:
                # Map alias to real table name
                table = cfg.ALIAS_MAP.get(alias)

                # Filter out joins (e.g. t.id = mc.movie_id)
                # We only want literals (value usually has quotes or is a number)
                is_join = not (val.startswith("'") or val.replace('.', '', 1).isdigit())

                if table and not is_join:
                    # Clean the value
                    clean_val = val.strip("'")

                    all_predicates.append({
                        "table": table,
                        "column": col,
                        "operator": op,
                        "value": clean_val,
                        "source_query": filename
                    })

    # Deduplicate (many queries share the same filters)
    # We convert to string JSON to dedup, then back
    unique_predicates = [json.loads(x) for x in set(json.dumps(obj) for obj in all_predicates)]

    output_file = os.path.join(cfg.OUTPUT_DIR, "queries.json")
    with open(output_file, 'w') as f:
        json.dump(unique_predicates, f, indent=4)

    print(f"Successfully extracted {len(unique_predicates)} unique single-table queries.")
    print(f"Saved to {output_file}")


if __name__ == "__main__":
    run()