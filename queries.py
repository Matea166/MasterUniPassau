import csv
import glob
import os
import re
import time
import collections
import sqlalchemy
from sqlalchemy import orm, text
import tqdm

# --- CONFIGURATION ---
DB_URI = 'postgresql://postgres:postgres@localhost:5433/job'
QUERY_DIR = '/Users/user/Desktop/join-order-benchmark/*.sql'
RESULTS_FILE = 'results_single_relation_final.csv'


def protect_sql_clauses(text):
    """
    Protects 'BETWEEN ... AND ...' and parentheses '( ... )' from being split by 'AND'.
    Replaces the internal 'AND' with a placeholder token.
    """
    # 1. Protect BETWEEN (e.g., BETWEEN 1950 AND 2000 -> BETWEEN 1950 <AND> 2000)
    # Matches: BETWEEN (value) AND (value)
    # Handles numbers and simple quoted strings
    pattern = r'(BETWEEN\s+[\w\d\']+\s+)AND(\s+[\w\d\']+)'
    while re.search(pattern, text, re.IGNORECASE):
        text = re.sub(pattern, r'\1<AND_PROTECTED>\2', text, flags=re.IGNORECASE)

    # 2. Protect Parentheses (e.g., (A AND B) -> (A <AND> B))
    # This is a simple recursive mask for one level of depth, usually sufficient for JOB
    if '(' in text:
        def replace_parens(match):
            content = match.group(0)
            return content.replace(' AND ', ' <AND_PROTECTED> ').replace(' and ', ' <AND_PROTECTED> ')

        text = re.sub(r'\([^)]+\)', replace_parens, text)

    return text


def restore_sql_clauses(text):
    """Restores the protected AND tokens."""
    return text.replace('<AND_PROTECTED>', ' AND ')


def extract_conditions_brute_force(sql, file_name):
    # 1. Clean Comments and Flatten
    lines = [line.split('--')[0] for line in sql.splitlines()]
    flat_sql = ' '.join(lines).replace('\n', ' ')

    # 2. Extract FROM ... WHERE
    match = re.search(r'FROM\s+(.+?)\s+WHERE\s+(.+)', flat_sql, re.IGNORECASE)
    if not match: return []

    from_section, raw_where = match.group(1), match.group(2)

    # 3. Extract Aliases
    aliases = {}
    for part in from_section.split(','):
        part = part.strip()
        tokens = part.split()
        if len(tokens) >= 2:
            if tokens[1].lower() == 'as':
                t_name, t_alias = tokens[0], tokens[2]
            else:
                t_name, t_alias = tokens[0], tokens[1]
            aliases[t_alias] = t_name
        elif len(tokens) == 1:
            aliases[tokens[0]] = tokens[0]

    # 4. Clean WHERE (Remove GROUP BY, etc)
    for term in ['GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT']:
        idx = re.search(rf'\s+{term}\s+', raw_where, re.IGNORECASE)
        if idx: raw_where = raw_where[:idx.start()]

    # 5. PROTECT & SPLIT
    protected_where = protect_sql_clauses(raw_where)

    # Split by AND (only the exposed ones)
    conditions = re.split(r'\s+AND\s+', protected_where, flags=re.IGNORECASE)

    table_conditions = collections.defaultdict(list)

    for cond in conditions:
        cond = cond.strip()
        if not cond: continue

        # Restore the protected ANDs inside this condition
        cond = restore_sql_clauses(cond)

        # SKIP JOINS (t1.col = t2.col)
        # Check if both sides of = look like table.col
        if re.search(r'[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\s*=\s*[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+', cond):
            continue

        # Assign to Table
        for alias in aliases:
            if re.search(rf'\b{alias}\.', cond):
                table_conditions[alias].append(cond)
                break

    # 6. Generate SQL
    results = []
    for alias, conds in table_conditions.items():
        if not conds: continue
        table = aliases[alias]
        clean_where = " AND ".join(conds)
        clean_where = clean_where.replace(';', '')

        results.append({
            'sql': f"SELECT * FROM {table} {alias} WHERE {clean_where}",
            'relations': [table],
            'wheres': conds
        })
    return results


if __name__ == '__main__':
    print("--- STARTING ROBUST RUN (WITH ROLLBACK) ---")

    engine = sqlalchemy.create_engine(DB_URI)
    session = orm.sessionmaker(bind=engine)()
    session.execute(text(f"SET statement_timeout = '{15 * 60}s'"))

    if os.path.exists(RESULTS_FILE): os.remove(RESULTS_FILE)

    with open(RESULTS_FILE, 'w') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'mother_query_name', 'sql', 'relations', 'joins', 'wheres',
            'true_cardinality', 'postgres_estimate', 'postgres_optimization_time', 'execution_time'
        ])
        writer.writeheader()

    files = sorted(glob.glob(QUERY_DIR))
    print(f"Found {len(files)} SQL files.")

    success_count = 0
    fail_count = 0

    with tqdm.tqdm(total=len(files)) as pbar:
        for file_path in files:
            query_name = os.path.basename(file_path).split('.')[0]
            if query_name in ['fkindexes', 'foreign_keys', 'schema']:
                pbar.update(1)
                continue

            try:
                content = open(file_path).read()
                queries = extract_conditions_brute_force(content, query_name)

                for q in queries:
                    sql = q['sql']
                    try:
                        # ESTIMATE
                        t0 = time.time()
                        res = session.execute(text(f"EXPLAIN {sql}")).first()
                        est_rows = float(res[0].split('rows=')[1].split(' ')[0])
                        t1 = time.time()

                        # COUNT
                        count_sql = re.sub(r'SELECT\s+\*', 'SELECT COUNT(*)', sql, count=1, flags=re.IGNORECASE)
                        t2 = time.time()
                        true_count = session.execute(text(count_sql)).first()[0]
                        t3 = time.time()

                        # SAVE
                        with open(RESULTS_FILE, 'a') as f:
                            writer = csv.DictWriter(f, fieldnames=[
                                'mother_query_name', 'sql', 'relations', 'joins', 'wheres',
                                'true_cardinality', 'postgres_estimate',
                                'postgres_optimization_time', 'execution_time'
                            ])
                            writer.writerow({
                                'mother_query_name': query_name,
                                'sql': sql,
                                'relations': q['relations'],
                                'joins': [],
                                'wheres': q['wheres'],
                                'true_cardinality': true_count,
                                'postgres_estimate': est_rows,
                                'postgres_optimization_time': t1 - t0,
                                'execution_time': t3 - t2
                            })
                        success_count += 1

                    except Exception as e:
                        fail_count += 1
                        # CRITICAL FIX: Rollback the transaction if error occurs
                        session.rollback()
                        continue

            except Exception as e:
                print(f"File Error {query_name}: {e}")

            pbar.update(1)

    print(f"\nDONE!")
    print(f"Queries Succeeded: {success_count}")
    print(f"Queries Failed:    {fail_count}")
    print(f"Results saved to:  {RESULTS_FILE}")