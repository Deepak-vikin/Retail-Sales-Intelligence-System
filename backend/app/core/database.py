import psycopg2
from .config import DATABASE_URL

def connection():
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SET timezone = 'Asia/Kolkata';")
    conn.commit()
    return conn
