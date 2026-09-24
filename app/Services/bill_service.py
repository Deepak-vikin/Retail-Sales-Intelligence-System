from app.core.database import connection


def get_bill(bill_id):
    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute("SELECT bill_id, cashier_id, transaction_datetime, payment_mode, total_amount FROM bills WHERE bill_id = %s;", (bill_id,))
        bill = cursor.fetchone()

        if not bill:
            return None

        cursor.execute("SELECT bi.item_id, bi.product_id, p.product_name, p.barcode, bi.quantity, bi.unit_price, bi.discount, bi.line_total FROM bill_items bi JOIN products p ON bi.product_id = p.product_id WHERE bi.bill_id = %s ORDER BY bi.item_id;", (bill_id,))
        items = cursor.fetchall()

        return {
            "bill": bill,
            "items": items
        }

    finally:
        conn.close()


def get_recent_bills(limit=100):
    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute("SELECT bill_id, cashier_id, transaction_datetime, payment_mode, total_amount FROM bills ORDER BY transaction_datetime DESC LIMIT %s;", (limit,))
        return cursor.fetchall()

    finally:
        conn.close()