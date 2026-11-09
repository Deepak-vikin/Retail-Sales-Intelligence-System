import psycopg2
import logging
from contextlib import contextmanager
from typing import Generator, Tuple, Optional
from .config import DATABASE_URL

logger = logging.getLogger(__name__)

def connection():
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute("SET timezone = 'Asia/Kolkata';")
    conn.commit()
    return conn

@contextmanager
def get_transaction(conn: Optional[psycopg2.extensions.connection] = None) -> Generator[Tuple[psycopg2.extensions.connection, psycopg2.extensions.cursor], None, None]:
    """
    Context manager for explicit transaction lifecycle management.
    1. Opens connection if not provided.
    2. Sets autocommit=False.
    3. Yields (conn, cur).
    4. Commits only after all operations succeed.
    5. On any exception, explicitly calls conn.rollback().
    6. Always closes cursor and connection in finally blocks.
    """
    close_conn = False
    if conn is None:
        conn = connection()
        close_conn = True

    conn.autocommit = False
    cur = conn.cursor()
    try:
        yield conn, cur
        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception as rb_err:
            logger.error("Transaction rollback failed: %s", type(rb_err).__name__)
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        if close_conn:
            try:
                conn.close()
            except Exception:
                pass

