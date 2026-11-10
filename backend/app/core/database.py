import psycopg2
from psycopg2.pool import ThreadedConnectionPool
import logging
import threading
from contextlib import contextmanager
from typing import Generator, Tuple, Optional
from .config import DATABASE_URL

logger = logging.getLogger(__name__)

_pool: Optional[ThreadedConnectionPool] = None
_pool_lock = threading.Lock()


def _get_pool() -> Optional[ThreadedConnectionPool]:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                try:
                    # Maintain between 1 and 10 persistent pooled connections to reduce TLS handshake overhead
                    _pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=DATABASE_URL)
                    logger.info("Initialized PostgreSQL ThreadedConnectionPool (min=1, max=10)")
                except Exception as e:
                    logger.warning("Could not initialize connection pool, falling back to direct connections: %s", e)
                    _pool = None
    return _pool


class PooledConnectionWrapper:
    """
    Transparent proxy around a pooled psycopg2 connection that intercepts close()
    to return the connection to the pool rather than closing the underlying socket.
    """
    def __init__(self, raw_conn: psycopg2.extensions.connection, pool: ThreadedConnectionPool):
        self._raw_conn = raw_conn
        self._pool = pool
        self._closed = False

    def cursor(self, *args, **kwargs):
        return self._raw_conn.cursor(*args, **kwargs)

    def commit(self):
        return self._raw_conn.commit()

    def rollback(self):
        return self._raw_conn.rollback()

    @property
    def autocommit(self):
        return self._raw_conn.autocommit

    @autocommit.setter
    def autocommit(self, val):
        self._raw_conn.autocommit = val

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                # Ensure clean transaction state before returning to pool
                if not self._raw_conn.closed and not self._raw_conn.autocommit:
                    self._raw_conn.rollback()
            except Exception:
                pass
            try:
                if self._raw_conn.closed:
                    self._pool.putconn(self._raw_conn, close=True)
                else:
                    self._pool.putconn(self._raw_conn)
            except Exception as e:
                logger.debug("Error returning connection to pool: %s", e)
                try:
                    self._raw_conn.close()
                except Exception:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __getattr__(self, name):
        return getattr(self._raw_conn, name)


def connection():
    """
    Acquire a database connection from the connection pool with Asia/Kolkata timezone set.
    Safely evicts stale or server-closed idle connections and falls back to direct connection if pooling is unavailable.
    """
    pool = _get_pool()
    if pool is not None:
        for attempt in range(2):
            raw_conn = None
            try:
                raw_conn = pool.getconn()
                if raw_conn.closed:
                    pool.putconn(raw_conn, close=True)
                    raw_conn = None
                    continue
                with raw_conn.cursor() as cur:
                    cur.execute("SET timezone = 'Asia/Kolkata';")
                raw_conn.commit()
                return PooledConnectionWrapper(raw_conn, pool)
            except Exception as e:
                if raw_conn is not None:
                    try:
                        pool.putconn(raw_conn, close=True)
                    except Exception:
                        pass
                if attempt == 0:
                    continue
                logger.warning("Pooled connection failed, falling back to direct connection: %s", e)

    # Fallback to direct connection
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
