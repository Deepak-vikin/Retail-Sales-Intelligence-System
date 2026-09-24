from app.core.database import connection

def get_suppliers():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT supplier_id, supplier_name, contact_number, payment_terms FROM suppliers ORDER BY supplier_id;")
        return cursor.fetchall()
    finally:
        conn.close()

def get_supplier(supplier_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT supplier_id, supplier_name, contact_number, payment_terms FROM suppliers WHERE supplier_id = %s;", (supplier_id,))
        return cursor.fetchone()
    finally:
        conn.close()

def get_supplier_products(supplier_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT p.product_id, p.barcode, p.product_name, p.category, p.cost_price, p.selling_price, p.reorder_level FROM products p JOIN purchases pu ON p.product_id = pu.product_id WHERE pu.supplier_id = %s ORDER BY p.product_name;", (supplier_id,))
        return cursor.fetchall()
    finally:
        conn.close()

def get_supplier_purchase_history(supplier_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT purchase_id, product_id, purchase_date, quantity_received, cost_price FROM purchases WHERE supplier_id = %s ORDER BY purchase_date DESC;", (supplier_id,))
        return cursor.fetchall()
    finally:
        conn.close()
