import csv
from collections import defaultdict
from decimal import Decimal

from psycopg2.extras import execute_values

from app.core.database import connection
from app.ingestion.csv_validator import validate_csv


def sync_daily_csv(file_path):
    errors = validate_csv(file_path)

    if errors:
        raise ValueError("\n".join(errors))

    bills = defaultdict(list)

    with open(file_path, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            bills[row["bill_id"]].append(row)

    if not bills:
        raise ValueError("Sales CSV contains no data.")

    conn = connection()

    try:
        cursor = conn.cursor()

        bill_ids = [int(bill_id) for bill_id in bills.keys()]

        cursor.execute(
            "SELECT bill_id FROM bills WHERE bill_id = ANY(%s);",
            (bill_ids,),
        )

        existing_bill_ids = {row[0] for row in cursor.fetchall()}

        duplicate_bill_ids = set(bill_ids) & existing_bill_ids

        if duplicate_bill_ids:
            raise ValueError(
                f"Bill IDs already exist: {sorted(duplicate_bill_ids)}"
            )

        cursor.execute(
            "SELECT COALESCE(MAX(item_id), 0) + 1 FROM bill_items;"
        )

        next_item_id = cursor.fetchone()[0]

        bill_rows = []
        item_rows = []
        inventory_changes = defaultdict(int)

        for bill_id, items in bills.items():

            first = items[0]

            total_amount = Decimal("0")

            for item in items:

                quantity = int(item["quantity"])
                unit_price = Decimal(item["unit_price"])
                discount = Decimal(item["discount"])

                line_total = (
                    Decimal(quantity) * unit_price
                ) - discount

                if line_total < 0:
                    raise ValueError(
                        f"Negative line total for bill_id {bill_id}, "
                        f"product_id {item['product_id']}"
                    )

                total_amount += line_total

                product_id = int(item["product_id"])

                inventory_changes[product_id] += quantity

                item_rows.append(
                    (
                        next_item_id,
                        int(bill_id),
                        product_id,
                        quantity,
                        unit_price,
                        discount,
                        line_total,
                    )
                )

                next_item_id += 1

            bill_rows.append(
                (
                    int(bill_id),
                    int(first["cashier_id"]),
                    first["transaction_datetime"],
                    first["payment_mode"],
                    total_amount,
                )
            )

        if bill_rows:
            execute_values(
                cursor,
                "INSERT INTO bills (bill_id, cashier_id, transaction_datetime, payment_mode, total_amount) VALUES %s;",
                bill_rows,
            )

        if item_rows:
            execute_values(
                cursor,
                "INSERT INTO bill_items (item_id, bill_id, product_id, quantity, unit_price, discount, line_total) VALUES %s;",
                item_rows,
            )

        for product_id, quantity_sold in inventory_changes.items():

            cursor.execute(
                "UPDATE inventory SET current_stock = current_stock - %s, last_updated = NOW() WHERE product_id = %s AND current_stock >= %s;",
                (
                    quantity_sold,
                    product_id,
                    quantity_sold,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Insufficient inventory or inventory record "
                    f"not found for product_id {product_id}. "
                    f"Required quantity: {quantity_sold}"
                )

        conn.commit()

        return {
            "bills_inserted": len(bill_rows),
            "bill_items_inserted": len(item_rows),
            "inventory_products_updated": len(inventory_changes),
            "units_sold": sum(inventory_changes.values()),
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()