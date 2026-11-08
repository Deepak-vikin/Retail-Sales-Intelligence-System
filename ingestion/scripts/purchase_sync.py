import csv
from decimal import Decimal

from psycopg2.extras import execute_values

from app.core.database import connection


def sync_purchase_csv(file_path):
    purchases = []

    with open(file_path, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        required_columns = {
            "purchase_id",
            "product_id",
            "supplier_id",
            "quantity_received",
            "cost_price",
            "purchase_date",
        }

        if not reader.fieldnames:
            raise ValueError("CSV has no header.")

        missing = required_columns - set(reader.fieldnames)

        if missing:
            raise ValueError(
                f"Missing columns: {', '.join(sorted(missing))}"
            )

        for row_number, row in enumerate(reader, start=2):
            try:
                purchase_id = int(row["purchase_id"])
                product_id = int(row["product_id"])
                supplier_id = int(row["supplier_id"])
                quantity_received = int(row["quantity_received"])
                cost_price = Decimal(row["cost_price"])

                if purchase_id <= 0:
                    raise ValueError("purchase_id must be positive")

                if product_id <= 0:
                    raise ValueError("product_id must be positive")

                if supplier_id <= 0:
                    raise ValueError("supplier_id must be positive")

                if quantity_received <= 0:
                    raise ValueError(
                        "quantity_received must be greater than 0"
                    )

                if cost_price < 0:
                    raise ValueError("cost_price cannot be negative")

                purchases.append(
                    (
                        purchase_id,
                        product_id,
                        supplier_id,
                        quantity_received,
                        cost_price,
                        row["purchase_date"],
                    )
                )

            except Exception as error:
                raise ValueError(
                    f"Row {row_number}: {error}"
                ) from error

    if not purchases:
        raise ValueError("Purchase CSV contains no data.")

    conn = connection()

    try:
        cursor = conn.cursor()

        product_ids = {row[1] for row in purchases}
        supplier_ids = {row[2] for row in purchases}
        purchase_ids = {row[0] for row in purchases}

        cursor.execute(
            "SELECT product_id FROM products WHERE product_id = ANY(%s);",
            (list(product_ids),),
        )

        existing_products = {row[0] for row in cursor.fetchall()}

        missing_products = product_ids - existing_products

        if missing_products:
            raise ValueError(
                f"Products do not exist: {sorted(missing_products)}"
            )

        cursor.execute(
            "SELECT supplier_id FROM suppliers WHERE supplier_id = ANY(%s);",
            (list(supplier_ids),),
        )

        existing_suppliers = {row[0] for row in cursor.fetchall()}

        missing_suppliers = supplier_ids - existing_suppliers

        if missing_suppliers:
            raise ValueError(
                f"Suppliers do not exist: {sorted(missing_suppliers)}"
            )

        cursor.execute(
            "SELECT purchase_id FROM purchases WHERE purchase_id = ANY(%s);",
            (list(purchase_ids),),
        )

        existing_purchases = {row[0] for row in cursor.fetchall()}

        duplicate_purchases = purchase_ids & existing_purchases

        if duplicate_purchases:
            raise ValueError(
                f"Purchase IDs already exist: {sorted(duplicate_purchases)}"
            )

        execute_values(
            cursor,
            "INSERT INTO purchases (purchase_id, product_id, supplier_id, quantity_received, cost_price, purchase_date) VALUES %s;",
            purchases,
        )

        for purchase in purchases:
            purchase_id, product_id, supplier_id, quantity, cost_price, purchase_date = purchase

            cursor.execute(
                "UPDATE inventory SET current_stock = current_stock + %s, last_updated = NOW() WHERE product_id = %s;",
                (quantity, product_id),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Inventory record not found for product_id {product_id}"
                )

        conn.commit()

        return {
            "purchases_inserted": len(purchases),
            "inventory_updated": len(purchases),
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()