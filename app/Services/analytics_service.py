from app.core.database import connection

def get_total_revenue():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(line_total) FROM bill_items;")
        return cursor.fetchone()[0] or 0.0
    finally:
        conn.close()

def get_total_units_sold():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(quantity) FROM bill_items;")
        return cursor.fetchone()[0] or 0
    finally:
        conn.close()

def get_total_bills():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT bill_id) FROM bills;")
        return cursor.fetchone()[0] or 0
    finally:
        conn.close()

def get_average_bill_value():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT AVG(total_amount) FROM bills;")
        return cursor.fetchone()[0] or 0.0
    finally:
        conn.close()

def get_sales_by_product():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.product_name, SUM(bi.line_total) as total_sales FROM bill_items bi JOIN products p ON bi.product_id = p.product_id GROUP BY p.product_name ORDER BY total_sales DESC;")
        return cursor.fetchall()
    finally:
        conn.close()

def get_sales_by_category():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.category, SUM(bi.line_total) as total_sales FROM bill_items bi JOIN products p ON bi.product_id = p.product_id GROUP BY p.category ORDER BY total_sales DESC;")
        return cursor.fetchall()
    finally:
        conn.close()

def get_units_sold_by_product():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.product_name, SUM(bi.quantity) as total_units FROM bill_items bi JOIN products p ON bi.product_id = p.product_id GROUP BY p.product_name ORDER BY total_units DESC;")
        return cursor.fetchall()
    finally:
        conn.close()

def get_units_sold_by_category():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.category, SUM(bi.quantity) as total_units FROM bill_items bi JOIN products p ON bi.product_id = p.product_id GROUP BY p.category ORDER BY total_units DESC;")
        return cursor.fetchall()
    finally:
        conn.close()

def get_top_selling_products(limit=10):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.product_name, SUM(bi.line_total) as total_sales FROM bill_items bi JOIN products p ON bi.product_id = p.product_id GROUP BY p.product_name ORDER BY total_sales DESC LIMIT %s;", (limit,))
        return cursor.fetchall()
    finally:
        conn.close()

def get_bottom_selling_products(limit=10):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.product_name, SUM(bi.line_total) as total_sales FROM bill_items bi JOIN products p ON bi.product_id = p.product_id GROUP BY p.product_name ORDER BY total_sales ASC LIMIT %s;", (limit,))
        return cursor.fetchall()
    finally:
        conn.close()

def get_sales_by_payment_mode():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT payment_mode, SUM(total_amount) as total_sales FROM bills GROUP BY payment_mode ORDER BY total_sales DESC;")
        return cursor.fetchall()
    finally:
        conn.close()

def get_daily_sales():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DATE(transaction_datetime) as sale_date, SUM(total_amount) as total_sales FROM bills GROUP BY DATE(transaction_datetime) ORDER BY sale_date DESC;")
        return cursor.fetchall()
    finally:
        conn.close()

def get_sales_for_date_range(start_date, end_date):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(bi.line_total) FROM bill_items bi JOIN bills b ON bi.bill_id = b.bill_id WHERE b.transaction_datetime >= %s AND b.transaction_datetime < %s;", (start_date, end_date))
        return cursor.fetchone()[0] or 0.0
    finally:
        conn.close()

def get_product_sales(product_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(line_total) FROM bill_items WHERE product_id = %s;", (product_id,))
        return cursor.fetchone()[0] or 0.0
    finally:
        conn.close()

def get_category_sales(category):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(bi.line_total) FROM bill_items bi JOIN products p ON bi.product_id = p.product_id WHERE p.category = %s;", (category,))
        return cursor.fetchone()[0] or 0.0
    finally:
        conn.close()

def get_low_stock_value():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(i.current_stock * p.cost_price) FROM inventory i JOIN products p ON i.product_id = p.product_id WHERE i.current_stock < p.reorder_level;")
        return cursor.fetchone()[0] or 0.0
    finally:
        conn.close()
