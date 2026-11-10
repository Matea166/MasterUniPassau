import os

import pandas as pd
import psycopg2


def main():
    db_name = os.environ.get("DB_NAME", "nhanes")
    db_user = os.environ.get("POSTGRES_USER", "postgres")
    db_password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    db_host = os.environ.get("POSTGRES_HOST", "postgres")
    db_port = os.environ.get("POSTGRES_PORT", "5432")
    csv_file = os.environ.get("CSV_FILE", "data/NHANES_age_prediction.csv")
    table_name = os.environ.get("TABLE_NAME", "nhanes_data")
    conn = psycopg2.connect(
        dbname=db_name, user=db_user, password=db_password, host=db_host, port=db_port
    )
    cur = conn.cursor()
    df = pd.read_csv(csv_file)
    cur.execute(f"TRUNCATE TABLE {table_name}")
    insert_query = f"""
INSERT INTO {table_name} (
    seqn, age_group, ridageyr, riagendr, paq605,
    bmxbmi, lbxglu, diq010, lbxglt, lbxin
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
    for _, row in df.iterrows():
        cur.execute(insert_query, tuple(row))
    conn.commit()
    cur.close()
    conn.close()
    print("CSV data inserted successfully!")


if __name__ == "__main__":
    main()
