import os

# --- PATHS ---
# Update this to your absolute path if needed
QUERIES_PATH = os.path.expanduser("/Users/user/Desktop/join-order-benchmark")
OUTPUT_DIR = "experiment_results"

# --- DATABASE ---
DB_CONFIG = {
    "dbname": "job",
    "user": "postgres",
    "password": "postgres",
    "host": "127.0.0.1",
    "port": "5433"
}

# --- ALIAS MAPPING ---
# The JOB queries use short aliases (e.g., 't'). We must map them to real tables.
ALIAS_MAP = {
    't': 'title',
    'ci': 'cast_info',
    'mi': 'movie_info',
    'mc': 'movie_companies',
    'mi_idx': 'movie_info_idx',
    'mk': 'movie_keyword',
    'n': 'name',
    'k': 'keyword',
    'cn': 'company_name',
    'ct': 'company_type',
    'it': 'info_type',
    'kt': 'kind_type',
    'rt': 'role_type',
    'chn': 'char_name',
    'an': 'aka_name',
    'at': 'aka_title',
    'cc': 'complete_cast',
    'cct1': 'comp_cast_type',
    'cct2': 'comp_cast_type',
    'lt': 'link_type',
    'ml': 'movie_link',
    'pi': 'person_info'
}

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs("datasets", exist_ok=True)
os.makedirs("problems", exist_ok=True)