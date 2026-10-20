
from datetime import datetime
import logging

from app.core.database import connection

logger = logging.getLogger(__name__)


def get_all_purchases():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT purchase_id, product_id, supplier_id,
                   purchase_date, quantity_received, cost_price
            FROM purchases
            ORDER BY purchase_id;
            """
        )
        return cursor.fetchall()
    finally:
        conn.close()


def get_purchase(purchase_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT purchase_id, product_id, supplier_id,
                   purchase_date, quantity_received, cost_price
            FROM purchases
            WHERE purchase_id = %s;
            """,
            (purchase_id,),
        )
        return cursor.fetchone()
    finally:
        conn.close()


def get_product_purchases(product_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT purchase_id, supplier_id, purchase_date,
                   quantity_received, cost_price
            FROM purchases
            WHERE product_id = %s
            ORDER BY purchase_date DESC;
            """,
            (product_id,),
        )
        return cursor.fetchall()
    finally:
        conn.close()


def get_recent_purchases(limit=10):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT purchase_id, product_id, supplier_id,
                   purchase_date, quantity_received, cost_price
            FROM purchases
            ORDER BY purchase_date DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return cursor.fetchall()
    finally:
        conn.close()


def get_total_purchased_quantity(product_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT SUM(quantity_received)
            FROM purchases
            WHERE product_id = %s;
            """,
            (product_id,),
        )
        return cursor.fetchone()[0] or 0
    finally:
        conn.close()


def get_total_purchase_cost(product_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT SUM(quantity_received * cost_price)
            FROM purchases
            WHERE product_id = %s;
            """,
            (product_id,),
        )
        return cursor.fetchone()[0] or 0.0
    finally:
        conn.close()


def get_purchases_for_date(target_date):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT purchase_id, product_id, supplier_id,
                   quantity_received, cost_price
            FROM purchases
            WHERE purchase_date = %s
            ORDER BY purchase_id;
            """,
            (target_date,),
        )
        return cursor.fetchall()
    finally:
        conn.close()


def create_purchase(
    purchase_id,
    product_id,
    supplier_id,
    quantity_received,
    cost_price,
    purchase_date,
):
    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM products WHERE product_id = %s;",
            (product_id,),
        )
        if cursor.fetchone() is None:
            raise ValueError(
                f"Product {product_id} does not exist."
            )

        cursor.execute(
            "SELECT 1 FROM suppliers WHERE supplier_id = %s;",
            (supplier_id,),
        )
        if cursor.fetchone() is None:
            raise ValueError(
                f"Supplier {supplier_id} does not exist."
            )

        cursor.execute(
            "SELECT 1 FROM purchases WHERE purchase_id = %s;",
            (purchase_id,),
        )
        if cursor.fetchone() is not None:
            raise ValueError(
                f"Purchase {purchase_id} already exists."
            )

        cursor.execute(
            """
            INSERT INTO purchases
                (purchase_id, product_id, supplier_id,
                 quantity_received, cost_price, purchase_date)
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            (
                purchase_id,
                product_id,
                supplier_id,
                quantity_received,
                cost_price,
                purchase_date,
            ),
        )

        cursor.execute(
            """
            UPDATE inventory
            SET current_stock = current_stock + %s,
                last_updated = %s
            WHERE product_id = %s;
            """,
            (
                quantity_received,
                datetime.now(),
                product_id,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"Inventory record for product {product_id} "
                "does not exist."
            )

        # Commit the purchase and stock increase first.
        conn.commit()

        # Refresh the daily summary without undoing a successful
        # purchase if the embedding service is temporarily unavailable.
        try:
            from app.rag.knowledge_generator import (
                refresh_daily_knowledge,
            )

            refresh_daily_knowledge(purchase_date)

        except Exception:
            logger.exception(
                "Purchase %s committed, but daily RAG refresh failed.",
                purchase_id,
            )

        return {
            "purchase_id": purchase_id,
            "product_id": product_id,
            "supplier_id": supplier_id,
            "quantity_received": quantity_received,
            "cost_price": cost_price,
            "purchase_date": str(purchase_date),
            "message": "Purchase recorded and inventory updated successfully.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
