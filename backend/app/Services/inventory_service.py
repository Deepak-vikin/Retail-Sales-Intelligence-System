from datetime import datetime
from decimal import Decimal

from app.core.database import connection


def get_inventory():
    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT i.inventory_id, i.product_id, p.product_name, p.barcode, p.category, i.current_stock, p.reorder_level, i.last_updated FROM inventory i JOIN products p ON i.product_id = p.product_id ORDER BY i.product_id;"
        )

        return cursor.fetchall()

    finally:
        conn.close()


def get_low_stock_products():
    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT i.product_id, p.product_name, p.barcode, p.category, i.current_stock, p.reorder_level FROM inventory i JOIN products p ON i.product_id = p.product_id WHERE i.current_stock < p.reorder_level ORDER BY i.current_stock ASC;"
        )

        return cursor.fetchall()

    finally:
        conn.close()


def get_stock_value():
    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT SUM(i.current_stock * p.cost_price) FROM inventory i JOIN products p ON i.product_id = p.product_id;"
        )

        return cursor.fetchone()[0] or Decimal("0")

    finally:
        conn.close()


def get_out_of_stock_products():
    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT i.product_id, p.product_name, p.barcode, p.category, i.current_stock, p.reorder_level FROM inventory i JOIN products p ON i.product_id = p.product_id WHERE i.current_stock = 0 ORDER BY p.product_name;"
        )

        return cursor.fetchall()

    finally:
        conn.close()


def reduce_stock(cursor, product_id, quantity):
    cursor.execute(
        "UPDATE inventory SET current_stock = current_stock - %s, last_updated = %s WHERE product_id = %s AND current_stock >= %s;",
        (quantity, datetime.now(), product_id, quantity)
    )

    if cursor.rowcount == 0:
        raise ValueError(
            f"Insufficient inventory for product_id {product_id}"
        )