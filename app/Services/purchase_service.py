from app.core.database import connection

def get_purchases():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT purchase_id, product_id, supplier_id, purchase_date, quantity_received, cost_price FROM purchases ORDER BY purchase_id;")
        return cursor.fetchall()
    finally:
        conn.close()

def get_purchase(purchase_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT purchase_id, product_id, supplier_id, purchase_date, quantity_received, cost_price FROM purchases WHERE purchase_id = %s;", (purchase_id,))
        return cursor.fetchone()
    finally:
        conn.close()

def get_product_purchases(product_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT purchase_id, supplier_id, purchase_date, quantity_received, cost_price FROM purchases WHERE product_id = %s ORDER BY purchase_date DESC;", (product_id,))
        return cursor.fetchall()
    finally:
        conn.close()

def get_recent_purchases(limit=10):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT purchase_id, product_id, supplier_id, purchase_date, quantity_received, cost_price FROM purchases ORDER BY purchase_date DESC LIMIT %s;", (limit,))
        return cursor.fetchall()
    finally:
        conn.close()

def get_total_purchased_quantity(product_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(quantity_received) FROM purchases WHERE product_id = %s;", (product_id,))
        return cursor.fetchone()[0] or 0
    finally:
        conn.close()

def get_total_purchase_cost(product_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(quantity_received * cost_price) FROM purchases WHERE product_id = %s;", (product_id,))
        return cursor.fetchone()[0] or 0.0
    finally:
        conn.close()
