from app.core.database import connection


def get_products():
    conn = connection()

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT product_id, barcode, product_name, category, cost_price, selling_price, reorder_level FROM products ORDER BY product_id;")
        return cursor.fetchall()

    finally:
        conn.close()