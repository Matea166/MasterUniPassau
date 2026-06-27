import pandas as pd
import psycopg2
import os

# SPECIFY THE NAME OF THE TABLE YOU WANT TO EXTRACT AS A STRING
TABLE = ""

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE_DIR, "data", f"{TABLE}.csv")

conn = psycopg2.connect(
    host="postgres",
    port=5432,
    dbname="imdb",
    user="postgres",
    password="postgres"
)

query = f"SELECT * FROM {TABLE};"
df = pd.read_sql(query, conn)

print(f"Loaded {len(df)} rows from {TABLE}")

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
df.to_csv(OUTPUT, index=False)
print(f"Saved to {OUTPUT}")

conn.close()
