import csv
from datetime import datetime
from app.core.database import connection

REQUIRED_COLUMNS = {
    "bill_id",
    "cashier_id",
    "transaction_datetime",
    "payment_mode",
    "product_id",
    "quantity",
    "unit_price",
    "discount"
}

def validate_csv(file_path):
    errors = []

    with open(file_path, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            return ["CSV has no header."]

        missing = REQUIRED_COLUMNS - set(reader.fieldnames)

        if missing:
            return [f"Missing columns: {', '.join(sorted(missing))}"]

        conn = connection()
        cursor = conn.cursor()
        cursor.execute("SELECT product_id FROM products;")
        existing_products = {row[0] for row in cursor.fetchall()}
        conn.close()

        for row_number, row in enumerate(reader, start=2):

            try:
                bill_id = int(row["bill_id"])
                if bill_id <= 0:
                    errors.append(f"Row {row_number}: bill_id must be positive")
            except:
                errors.append(f"Row {row_number}: invalid bill_id")

            try:
                cashier_id = int(row["cashier_id"])
                if cashier_id <= 0:
                    errors.append(f"Row {row_number}: cashier_id must be positive")
            except:
                errors.append(f"Row {row_number}: invalid cashier_id")

            try:
                product_id = int(row["product_id"])

                if product_id <= 0:
                    errors.append(f"Row {row_number}: product_id must be positive")

                elif product_id not in existing_products:
                    errors.append(
                        f"Row {row_number}: product_id {product_id} does not exist"
                    )

            except:
                errors.append(f"Row {row_number}: invalid product_id")

            try:
                quantity = int(row["quantity"])

                if quantity <= 0:
                    errors.append(
                        f"Row {row_number}: quantity must be greater than 0"
                    )

            except:
                errors.append(f"Row {row_number}: invalid quantity")

            try:
                unit_price = float(row["unit_price"])

                if unit_price < 0:
                    errors.append(
                        f"Row {row_number}: unit_price cannot be negative"
                    )

            except:
                errors.append(f"Row {row_number}: invalid unit_price")

            try:
                discount = float(row["discount"])

                if discount < 0:
                    errors.append(
                        f"Row {row_number}: discount cannot be negative"
                    )

            except:
                errors.append(f"Row {row_number}: invalid discount")

            try:
                if float(row["discount"]) > float(row["quantity"]) * float(row["unit_price"]):
                    errors.append(
                        f"Row {row_number}: discount exceeds line amount"
                    )
            except:
                pass

            try:
                datetime.fromisoformat(row["transaction_datetime"])
            except:
                errors.append(
                    f"Row {row_number}: invalid transaction_datetime"
                )

            if not row["payment_mode"].strip():
                errors.append(
                    f"Row {row_number}: payment_mode is empty"
                )

    return errors