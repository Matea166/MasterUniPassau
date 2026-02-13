import psycopg2
import pandas as pd

# ---------- CONFIG ----------
DB_NAME = "nhanes"
DB_USER = "postgres"
DB_PASSWORD = "postgres"
DB_HOST = "localhost"
DB_PORT = "5433"

CSV_FILE = "data/NHANES_age_prediction.csv"
TABLE_NAME = "nhanes_data"
# ----------------------------

# Connect to PostgreSQL
conn = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT
)

cur = conn.cursor()

# Read CSV
df = pd.read_csv(CSV_FILE)

# Insert query
insert_query = f"""
INSERT INTO {TABLE_NAME} (
    seqn, age_group, ridageyr, riagendr, paq605,
    bmxbmi, lbxglu, diq010, lbxglt, lbxin
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

# Insert rows
for _, row in df.iterrows():
    cur.execute(insert_query, tuple(row))

# Commit and close
conn.commit()
cur.close()
conn.close()

print("CSV data inserted successfully!")
