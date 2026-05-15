
import psycopg
import os

DB_URL = "postgresql://postgres:postgres@localhost:5432/guepard" # standard local
if os.getenv("DATABASE_URL"): DB_URL = os.getenv("DATABASE_URL")

try:
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source_filename, count(*), sum(length(content)) FROM corporate_knowledge GROUP BY source_filename")
            for row in cur.fetchall():
                print(f"File: {row[0]} | Chunks: {row[1]} | Total Chars: {row[2]}")
except Exception as e:
    print(f"Error: {e}")
