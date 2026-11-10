import os

import pandas as pd
import psycopg2


def main():
    db_name = os.environ.get("DB_NAME", "wetgrass")
    db_user = os.environ.get("POSTGRES_USER", "postgres")
    db_password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    db_host = os.environ.get("POSTGRES_HOST", "postgres")
    db_port = os.environ.get("POSTGRES_PORT", "5432")
    csv_file = os.environ.get("CSV_FILE", "data/WetGrass_variance_zero.csv")
    table_name = os.environ.get("TABLE_NAME", "wetgrass_data")
    conn = psycopg2.connect(
        dbname=db_name, user=db_user, password=db_password, host=db_host, port=db_port
    )
    cur = conn.cursor()
    df = pd.read_csv(csv_file)
    cur.execute(f"TRUNCATE TABLE {table_name}")
    columns = [c.lower() for c in df.columns]
    placeholders = ", ".join(["%s"] * len(columns))
    insert_query = (
        f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
    )
    for _, row in df.iterrows():
        cur.execute(
            insert_query, tuple((v.item() if hasattr(v, "item") else v for v in row))
        )
    conn.commit()
    cur.execute(f"ANALYZE {table_name}")
    conn.commit()
    cur.close()
    conn.close()
    print(f"Imported {len(df)} rows from {csv_file} into {db_name}.{table_name}")


if __name__ == "__main__":
    main()
