import psycopg2
import pandas as pd

# ---------- CONFIG ----------
DB_NAME = "wetgrass_variance_nonzero"
DB_USER = "postgres"
DB_PASSWORD = "postgres"
DB_HOST = "localhost"
DB_PORT = "5432"

CSV_FILE = "data/WetGrass_variance_non_zero.csv"
TABLE_NAME = "wetgrass_data"
# ----------------------------

# Connect to PostgreSQL
conn = psycopg2.connect(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=os.getenv("POSTGRES_PORT", "5432"),
    database=os.getenv("POSTGRES_DB", "imdb"),
    user=os.getenv("POSTGRES_USER", "postgres"),
    password=os.getenv("POSTGRES_PASSWORD", "postgres"),
)

cur = conn.cursor()

# Read CSV
df = pd.read_csv(CSV_FILE)

# Insert query
insert_query = f"""
INSERT INTO {TABLE_NAME} (
    cloud, sprinkler, rain, wetgrass
)
VALUES (%s, %s, %s, %s)
"""

# Insert rows
for _, row in df.iterrows():
    cur.execute(insert_query, tuple(row))

# Commit and close
conn.commit()
cur.close()
conn.close()

print("CSV data inserted successfully!")
