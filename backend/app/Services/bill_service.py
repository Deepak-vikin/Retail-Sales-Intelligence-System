from datetime import datetime
from decimal import Decimal
import logging
import time
import threading
from psycopg2.extras import execute_values

from app.core.database import connection

logger = logging.getLogger(__name__)


def _background_refresh_daily_knowledge(refresh_date, bill_id):
    """Asynchronously generate daily RAG knowledge and embeddings without blocking checkout."""
    try:
        from app.rag.knowledge_generator import refresh_daily_knowledge
        refresh_daily_knowledge(refresh_date)
        logger.info("[PERF] Daily RAG knowledge refreshed asynchronously for bill %s", bill_id)
    except Exception:
        logger.exception("Daily RAG knowledge refresh failed in background for bill %s", bill_id)


def get_bill(bill_id):
    t0 = time.perf_counter()
    conn = connection()

    try:
        cursor = conn.cursor()

        # Single-roundtrip query combining bill metadata and aggregated items
        cursor.execute(
            """
            SELECT 
                b.bill_id, b.cashier_id, b.transaction_datetime, b.payment_mode, b.total_amount,
                COALESCE(
                    json_agg(
                        json_build_array(
                            bi.item_id,
                            bi.product_id,
                            p.product_name,
                            p.barcode,
                            bi.quantity,
                            bi.unit_price,
                            bi.discount,
                            bi.line_total
                        ) ORDER BY bi.item_id
                    ) FILTER (WHERE bi.item_id IS NOT NULL),
                    '[]'::json
                ) AS items
            FROM bills b
            LEFT JOIN bill_items bi ON b.bill_id = bi.bill_id
            LEFT JOIN products p ON bi.product_id = p.product_id
            WHERE b.bill_id = %s
            GROUP BY b.bill_id, b.cashier_id, b.transaction_datetime, b.payment_mode, b.total_amount;
            """,
            (bill_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        bill = (row[0], row[1], row[2], row[3], row[4])
        # Convert items to list of tuples to strictly adhere to existing API and PDF generator contract
        items = [tuple(it) for it in row[5]]

        dur = (time.perf_counter() - t0) * 1000
        logger.info("[PERF] get_bill #%s completed in %.2fms", bill_id, dur)

        return {"bill": bill, "items": items}

    finally:
        conn.close()


def get_recent_bills(limit=50):
    t0 = time.perf_counter()
    conn = connection()

    try:
        cursor = conn.cursor()

        # CTE optimization: restrict and order the top 50 bills before joining items
        cursor.execute(
            """
            WITH top_bills AS (
                SELECT bill_id, cashier_id, transaction_datetime, payment_mode, total_amount
                FROM bills
                ORDER BY transaction_datetime DESC, bill_id DESC
                LIMIT %s
            )
            SELECT tb.bill_id, tb.cashier_id, tb.transaction_datetime,
                   tb.payment_mode, tb.total_amount,
                   COALESCE(COUNT(bi.item_id), 0) AS item_count
            FROM top_bills tb
            LEFT JOIN bill_items bi ON tb.bill_id = bi.bill_id
            GROUP BY tb.bill_id, tb.cashier_id, tb.transaction_datetime, tb.payment_mode, tb.total_amount
            ORDER BY tb.transaction_datetime DESC, tb.bill_id DESC;
            """,
            (limit,),
        )
        results = cursor.fetchall()
        dur = (time.perf_counter() - t0) * 1000
        logger.info("[PERF] get_recent_bills(limit=%d) fetched %d records in %.2fms", limit, len(results), dur)
        return results

    finally:
        conn.close()


def search_bills(query: str, limit: int = 50):
    t0 = time.perf_counter()
    conn = connection()

    try:
        cursor = conn.cursor()
        clean_q = query.strip()
        upper_q = clean_q.upper()
        if upper_q.startswith("BILL-"):
            clean_q = clean_q[5:]
        elif upper_q.startswith("BILL"):
            clean_q = clean_q[4:]
        if clean_q.startswith("#"):
            clean_q = clean_q[1:]
        clean_q = clean_q.strip()

        if not clean_q:
            return []

        # CTE optimization: filter matching bills first before joining items
        cursor.execute(
            """
            WITH matched_bills AS (
                SELECT bill_id, cashier_id, transaction_datetime, payment_mode, total_amount
                FROM bills
                WHERE CAST(bill_id AS TEXT) LIKE %s
                ORDER BY transaction_datetime DESC, bill_id DESC
                LIMIT %s
            )
            SELECT mb.bill_id, mb.cashier_id, mb.transaction_datetime,
                   mb.payment_mode, mb.total_amount,
                   COALESCE(COUNT(bi.item_id), 0) AS item_count
            FROM matched_bills mb
            LEFT JOIN bill_items bi ON mb.bill_id = bi.bill_id
            GROUP BY mb.bill_id, mb.cashier_id, mb.transaction_datetime, mb.payment_mode, mb.total_amount
            ORDER BY mb.transaction_datetime DESC, mb.bill_id DESC;
            """,
            (f"%{clean_q}%", limit),
        )
        results = cursor.fetchall()
        dur = (time.perf_counter() - t0) * 1000
        logger.info("[PERF] search_bills(query='%s') fetched %d records in %.2fms", clean_q, len(results), dur)
        return results

    finally:
        conn.close()


def create_bill(
    bill_id,
    cashier_id,
    transaction_datetime,
    payment_mode,
    items,
):
    t_start = time.perf_counter()
    conn = connection()

    try:
        cursor = conn.cursor()

        # 1. Duplicate bill check
        cursor.execute(
            "SELECT 1 FROM bills WHERE bill_id = %s;",
            (bill_id,),
        )
        if cursor.fetchone() is not None:
            raise ValueError(f"Bill {bill_id} already exists.")

        if not items:
            raise ValueError("Bill must contain at least one item.")

        # 2. Batch query products and lock inventory stocks atomically in a single roundtrip
        prod_ids = list({item["product_id"] for item in items})
        cursor.execute(
            """
            SELECT p.product_id, p.product_name, inv.current_stock
            FROM products p
            JOIN inventory inv ON p.product_id = inv.product_id
            WHERE p.product_id = ANY(%s)
            FOR UPDATE OF inv;
            """,
            (prod_ids,),
        )
        prod_rows = cursor.fetchall()
        prod_map = {row[0]: {"name": row[1], "stock": row[2]} for row in prod_rows}

        if len(prod_map) < len(prod_ids):
            # Check which product or inventory is missing to provide exact error message
            cursor.execute("SELECT product_id FROM products WHERE product_id = ANY(%s);", (prod_ids,))
            existing_pids = {r[0] for r in cursor.fetchall()}
            for pid in prod_ids:
                if pid not in existing_pids:
                    raise ValueError(f"Product {pid} does not exist.")
                if pid not in prod_map:
                    raise ValueError(f"Inventory record for product {pid} does not exist.")

        # Aggregate total requested quantities per product
        total_requested = {}
        for item in items:
            pid = item["product_id"]
            total_requested[pid] = total_requested.get(pid, 0) + item["quantity"]

        prepared_items = []
        total_amount = Decimal("0")

        # 3. Item-level validation
        for item in items:
            product_id = item["product_id"]
            quantity = item["quantity"]
            unit_price = Decimal(str(item["unit_price"]))
            discount = Decimal(str(item.get("discount", 0)))

            if quantity <= 0:
                raise ValueError(
                    f"Quantity must be greater than zero for product {product_id}."
                )

            if unit_price < 0:
                raise ValueError(
                    f"Unit price cannot be negative for product {product_id}."
                )

            if discount < 0:
                raise ValueError(
                    f"Discount cannot be negative for product {product_id}."
                )

            inv_stock = prod_map[product_id]["stock"]
            req_qty = total_requested[product_id]
            if inv_stock < req_qty:
                raise ValueError(
                    f"Insufficient inventory for product {product_id}. "
                    f"Available: {inv_stock}, requested: {req_qty}"
                )

            line_total = (unit_price * quantity) - discount
            if line_total < 0:
                raise ValueError(
                    f"Line total cannot be negative for product {product_id}."
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

        t_val = time.perf_counter()

        # 4. Insert bill record
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

        # 5. Get next item_id
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

        # 6. Batch insert bill_items using execute_values
        bill_item_tuples = []
        for it in prepared_items:
            bill_item_tuples.append((
                next_item_id,
                bill_id,
                it["product_id"],
                it["quantity"],
                it["unit_price"],
                it["discount"],
                it["line_total"],
            ))
            next_item_id += 1

        execute_values(
            cursor,
            """
            INSERT INTO bill_items
                (item_id, bill_id, product_id, quantity,
                 unit_price, discount, line_total)
            VALUES %s;
            """,
            bill_item_tuples,
        )

        # 7. Batch update inventory stocks in a single roundtrip
        inv_updates = [(pid, req_qty) for pid, req_qty in total_requested.items()]
        execute_values(
            cursor,
            """
            UPDATE inventory AS inv
            SET current_stock = inv.current_stock - v.qty,
                last_updated = NOW()
            FROM (VALUES %s) AS v(product_id, qty)
            WHERE inv.product_id = v.product_id;
            """,
            inv_updates,
            template="(%s, %s)",
        )

        conn.commit()
        t_commit = time.perf_counter()

        dur_val = (t_val - t_start) * 1000
        dur_write = (t_commit - t_val) * 1000
        dur_total = (t_commit - t_start) * 1000
        logger.info(
            "[PERF] create_bill #%s (items=%d) committed in %.2fms (validation=%.2fms, writes=%.2fms)",
            bill_id,
            len(prepared_items),
            dur_total,
            dur_val,
            dur_write,
        )

        # 8. Asynchronously refresh daily RAG knowledge in background daemon thread
        refresh_date = (
            transaction_datetime.date()
            if isinstance(transaction_datetime, datetime)
            else transaction_datetime
        )
        threading.Thread(
            target=_background_refresh_daily_knowledge,
            args=(refresh_date, bill_id),
            daemon=True,
            name=f"rag-refresh-{bill_id}",
        ).start()

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
