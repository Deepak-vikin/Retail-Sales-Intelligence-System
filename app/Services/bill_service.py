
from datetime import datetime
from decimal import Decimal
import logging

from app.core.database import connection

logger = logging.getLogger(__name__)


def get_bill(bill_id):
    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT bill_id, cashier_id, transaction_datetime,
                   payment_mode, total_amount
            FROM bills
            WHERE bill_id = %s;
            """,
            (bill_id,),
        )
        bill = cursor.fetchone()

        if not bill:
            return None

        cursor.execute(
            """
            SELECT bi.item_id, bi.product_id, p.product_name,
                   p.barcode, bi.quantity, bi.unit_price,
                   bi.discount, bi.line_total
            FROM bill_items bi
            JOIN products p ON bi.product_id = p.product_id
            WHERE bi.bill_id = %s
            ORDER BY bi.item_id;
            """,
            (bill_id,),
        )
        items = cursor.fetchall()

        return {"bill": bill, "items": items}

    finally:
        conn.close()


def get_recent_bills(limit=100):
    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT bill_id, cashier_id, transaction_datetime,
                   payment_mode, total_amount
            FROM bills
            ORDER BY transaction_datetime DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return cursor.fetchall()

    finally:
        conn.close()


def create_bill(
    bill_id,
    cashier_id,
    transaction_datetime,
    payment_mode,
    items,
):
    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM bills WHERE bill_id = %s;",
            (bill_id,),
        )

        if cursor.fetchone() is not None:
            raise ValueError(f"Bill {bill_id} already exists.")

        if not items:
            raise ValueError("Bill must contain at least one item.")

        prepared_items = []
        total_amount = Decimal("0")

        for item in items:
            product_id = item["product_id"]
            quantity = item["quantity"]
            unit_price = Decimal(str(item["unit_price"]))
            discount = Decimal(str(item.get("discount", 0)))

            if quantity <= 0:
                raise ValueError(
                    f"Quantity must be greater than zero "
                    f"for product {product_id}."
                )

            if unit_price < 0:
                raise ValueError(
                    f"Unit price cannot be negative "
                    f"for product {product_id}."
                )

            if discount < 0:
                raise ValueError(
                    f"Discount cannot be negative "
                    f"for product {product_id}."
                )

            cursor.execute(
                "SELECT product_name FROM products WHERE product_id = %s;",
                (product_id,),
            )

            if cursor.fetchone() is None:
                raise ValueError(
                    f"Product {product_id} does not exist."
                )

            cursor.execute(
                """
                SELECT current_stock
                FROM inventory
                WHERE product_id = %s
                FOR UPDATE;
                """,
                (product_id,),
            )

            inventory = cursor.fetchone()

            if inventory is None:
                raise ValueError(
                    f"Inventory record for product {product_id} "
                    "does not exist."
                )

            current_stock = inventory[0]

            if current_stock < quantity:
                raise ValueError(
                    f"Insufficient inventory for product {product_id}. "
                    f"Available: {current_stock}, requested: {quantity}"
                )

            line_total = (unit_price * quantity) - discount

            if line_total < 0:
                raise ValueError(
                    f"Line total cannot be negative "
                    f"for product {product_id}."
                )

            total_amount += line_total

            prepared_items.append(
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "discount": discount,
                    "line_total": line_total,
                }
            )

        cursor.execute(
            """
            INSERT INTO bills
                (bill_id, cashier_id, transaction_datetime,
                 payment_mode, total_amount)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (
                bill_id,
                cashier_id,
                transaction_datetime,
                payment_mode,
                total_amount,
            ),
        )

        # Preserve the existing item-ID allocation approach.
        cursor.execute(
            """
            SELECT item_id
            FROM bill_items
            ORDER BY item_id DESC
            LIMIT 1
            FOR UPDATE;
            """
        )

        last_item = cursor.fetchone()
        next_item_id = (last_item[0] if last_item else 0) + 1

        for item in prepared_items:
            cursor.execute(
                """
                INSERT INTO bill_items
                    (item_id, bill_id, product_id, quantity,
                     unit_price, discount, line_total)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    next_item_id,
                    bill_id,
                    item["product_id"],
                    item["quantity"],
                    item["unit_price"],
                    item["discount"],
                    item["line_total"],
                ),
            )

            cursor.execute(
                """
                UPDATE inventory
                SET current_stock = current_stock - %s,
                    last_updated = %s
                WHERE product_id = %s;
                """,
                (
                    item["quantity"],
                    datetime.now(),
                    item["product_id"],
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Failed to update inventory for product "
                    f"{item['product_id']}."
                )

            next_item_id += 1

        # Commit the bill, its items, and inventory changes first.
        conn.commit()

        # RAG refresh is best-effort: a refresh failure must not
        # turn a successfully committed sale into a failed response.
        try:
            from app.rag.knowledge_generator import (
                refresh_daily_knowledge,
            )

            refresh_date = (
                transaction_datetime.date()
                if isinstance(transaction_datetime, datetime)
                else transaction_datetime
            )

            refresh_daily_knowledge(refresh_date)

        except Exception:
            logger.exception(
                "Bill %s committed, but daily RAG refresh failed.",
                bill_id,
            )

        return {
            "bill_id": bill_id,
            "cashier_id": cashier_id,
            "transaction_datetime": str(transaction_datetime),
            "payment_mode": payment_mode,
            "total_amount": total_amount,
            "items": prepared_items,
            "message": "Bill created and inventory updated successfully.",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
