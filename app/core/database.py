import psycopg2
from .config import DATABASE_URL

def connection():
    return psycopg2.connect(DATABASE_URL)
