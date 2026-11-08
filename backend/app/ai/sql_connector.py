from app.core.database import connection
from app.ai.sql_validaator import SQLValidator


def execute_sql(sql):
    sql = SQLValidator.validate(sql)

    conn = connection()

    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        return cursor.fetchall()
    finally:
        conn.close()