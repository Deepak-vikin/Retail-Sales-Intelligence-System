"""
Integration test – database connectivity.

Verifies that the application can open and close a connection to the
configured PostgreSQL database.
"""
from app.core.database import connection


def test_database_connection():
    """Database connection can be opened and closed successfully."""
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        result = cursor.fetchone()
        assert result == (1,), f"Unexpected result from DB: {result}"
    finally:
        conn.close()
