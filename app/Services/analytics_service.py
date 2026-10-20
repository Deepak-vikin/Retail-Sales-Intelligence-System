from app.core.database import connection


def get_total_revenue():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(total_amount), 0) FROM bills;")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_total_units_sold():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(quantity), 0) FROM bill_items;")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_total_bills():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bills;")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_average_bill_value():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(AVG(total_amount), 0) FROM bills;")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_today_bills():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bills WHERE transaction_datetime::date = CURRENT_DATE;")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_today_revenue():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(total_amount), 0) FROM bills WHERE transaction_datetime::date = CURRENT_DATE;")
        return float(cursor.fetchone()[0])
    finally:
        conn.close()


def get_today_units_sold():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(SUM(bi.quantity), 0)
            FROM bills b
            JOIN bill_items bi ON b.bill_id = bi.bill_id
            WHERE b.transaction_datetime::date = CURRENT_DATE;
        """)
        return int(cursor.fetchone()[0])
    finally:
        conn.close()


def get_today_average_bill_value():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COALESCE(SUM(total_amount), 0) AS revenue,
                COUNT(*) AS bills_count
            FROM bills
            WHERE transaction_datetime::date = CURRENT_DATE;
        """)
        row = cursor.fetchone()
        revenue = float(row[0] or 0)
        bills_count = int(row[1] or 0)
        return (revenue / bills_count) if bills_count > 0 else 0.0
    finally:
        conn.close()


def get_yesterday_bills():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bills WHERE transaction_datetime::date = CURRENT_DATE - INTERVAL '1 day';")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_yesterday_revenue():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(total_amount), 0) FROM bills WHERE transaction_datetime::date = CURRENT_DATE - INTERVAL '1 day';")
        return float(cursor.fetchone()[0])
    finally:
        conn.close()


def get_today_vs_yesterday_comparison():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(CASE WHEN transaction_datetime::date = CURRENT_DATE THEN 1 END) AS today_bills,
                COUNT(CASE WHEN transaction_datetime::date = CURRENT_DATE - INTERVAL '1 day' THEN 1 END) AS yesterday_bills,
                COALESCE(SUM(CASE WHEN transaction_datetime::date = CURRENT_DATE THEN total_amount ELSE 0 END), 0) AS today_revenue,
                COALESCE(SUM(CASE WHEN transaction_datetime::date = CURRENT_DATE - INTERVAL '1 day' THEN total_amount ELSE 0 END), 0) AS yesterday_revenue
            FROM bills
            WHERE transaction_datetime::date >= CURRENT_DATE - INTERVAL '1 day'
              AND transaction_datetime::date <= CURRENT_DATE;
        """)
        row = cursor.fetchone()
        today_bills = int(row[0] or 0)
        yesterday_bills = int(row[1] or 0)
        today_revenue = float(row[2] or 0)
        yesterday_revenue = float(row[3] or 0)

        # Calculate bills percentage change
        if yesterday_bills > 0:
            bills_pct = round(((today_bills - yesterday_bills) / yesterday_bills) * 100, 1)
            if bills_pct > 0:
                bills_trend = f"↑ +{bills_pct}% volume"
            elif bills_pct < 0:
                bills_trend = f"↓ {bills_pct}% volume"
            else:
                bills_trend = "0.0% vs yesterday"
        elif today_bills > 0:
            bills_pct = None
            bills_trend = f"+{today_bills} bills (no transactions yesterday)"
        else:
            bills_pct = None
            bills_trend = "No transactions yesterday"

        # Calculate revenue percentage change
        if yesterday_revenue > 0:
            rev_pct = round(((today_revenue - yesterday_revenue) / yesterday_revenue) * 100, 1)
            if rev_pct > 0:
                rev_trend = f"↑ +{rev_pct}% vs yesterday"
            elif rev_pct < 0:
                rev_trend = f"↓ {rev_pct}% vs yesterday"
            else:
                rev_trend = "0.0% vs yesterday"
        elif today_revenue > 0:
            rev_pct = None
            rev_trend = f"+₹{today_revenue:,.2f} (no revenue yesterday)"
        else:
            rev_pct = None
            rev_trend = "No transactions yesterday"

        return {
            "today_bills": today_bills,
            "yesterday_bills": yesterday_bills,
            "bills_percentage_change": bills_pct,
            "bills_trend_text": bills_trend,
            "today_revenue": today_revenue,
            "yesterday_revenue": yesterday_revenue,
            "revenue_percentage_change": rev_pct,
            "revenue_trend_text": rev_trend,
        }
    finally:
        conn.close()


def get_today_summary():
    comp = get_today_vs_yesterday_comparison()
    units = get_today_units_sold()
    bills = comp["today_bills"]
    revenue = comp["today_revenue"]
    avg_bill = (revenue / bills) if bills > 0 else 0.0

    return {
        "revenue": revenue,
        "bills": bills,
        "units_sold": units,
        "average_bill_value": avg_bill,
        "bills_trend_text": comp["bills_trend_text"],
        "revenue_trend_text": comp["revenue_trend_text"],
        "comparison": comp
    }




def get_sales_by_product():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.product_id, p.product_name, COALESCE(SUM(bi.line_total), 0) AS sales FROM bill_items bi JOIN products p ON bi.product_id = p.product_id GROUP BY p.product_id, p.product_name ORDER BY sales DESC;")
        return cursor.fetchall()
    finally:
        conn.close()


def get_sales_by_category():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.category, COALESCE(SUM(bi.line_total), 0) AS sales FROM bill_items bi JOIN products p ON bi.product_id = p.product_id GROUP BY p.category ORDER BY sales DESC;")
        return cursor.fetchall()
    finally:
        conn.close()


def get_units_sold_by_product():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.product_id, p.product_name, COALESCE(SUM(bi.quantity), 0) AS units_sold FROM bill_items bi JOIN products p ON bi.product_id = p.product_id GROUP BY p.product_id, p.product_name ORDER BY units_sold DESC;")
        return cursor.fetchall()
    finally:
        conn.close()


def get_units_sold_by_category():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.category, COALESCE(SUM(bi.quantity), 0) AS units_sold FROM bill_items bi JOIN products p ON bi.product_id = p.product_id GROUP BY p.category ORDER BY units_sold DESC;")
        return cursor.fetchall()
    finally:
        conn.close()


def get_top_selling_products(limit=10):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.product_id, p.product_name, COALESCE(SUM(bi.quantity), 0) AS units_sold FROM bill_items bi JOIN products p ON bi.product_id = p.product_id GROUP BY p.product_id, p.product_name ORDER BY units_sold DESC LIMIT %s;", (limit,))
        return cursor.fetchall()
    finally:
        conn.close()


def get_bottom_selling_products(limit=10):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.product_id, p.product_name, COALESCE(SUM(bi.quantity), 0) AS units_sold FROM bill_items bi JOIN products p ON bi.product_id = p.product_id GROUP BY p.product_id, p.product_name ORDER BY units_sold ASC LIMIT %s;", (limit,))
        return cursor.fetchall()
    finally:
        conn.close()


def get_sales_by_payment_mode():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT payment_mode, COALESCE(SUM(total_amount), 0) AS sales FROM bills GROUP BY payment_mode ORDER BY sales DESC;")
        return cursor.fetchall()
    finally:
        conn.close()


def get_daily_sales():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT transaction_datetime::date AS sale_date, COALESCE(SUM(total_amount), 0) AS sales FROM bills GROUP BY sale_date ORDER BY sale_date;")
        return cursor.fetchall()
    finally:
        conn.close()


def get_sales_for_date_range(start_date, end_date):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(total_amount), 0) FROM bills WHERE transaction_datetime::date BETWEEN %s AND %s;", (start_date, end_date))
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_product_sales(product_id):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.product_id, p.product_name, COALESCE(SUM(bi.line_total), 0) AS sales FROM bill_items bi JOIN products p ON bi.product_id = p.product_id WHERE p.product_id = %s GROUP BY p.product_id, p.product_name;", (product_id,))
        return cursor.fetchone()
    finally:
        conn.close()


def get_category_sales(category):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.category, COALESCE(SUM(bi.line_total), 0) AS sales FROM bill_items bi JOIN products p ON bi.product_id = p.product_id WHERE p.category = %s GROUP BY p.category;", (category,))
        return cursor.fetchone()
    finally:
        conn.close()


def get_low_stock_value():
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(i.current_stock * p.cost_price), 0) FROM inventory i JOIN products p ON i.product_id = p.product_id WHERE i.current_stock <= p.reorder_level;")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_daily_sales_for_date(target_date):
    conn = connection()
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT COALESCE(SUM(total_amount), 0) FROM bills WHERE transaction_datetime::date = %s;", (target_date,))
        revenue = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM bills WHERE transaction_datetime::date = %s;", (target_date,))
        bills = cursor.fetchone()[0]

        cursor.execute("SELECT COALESCE(SUM(bi.quantity), 0) FROM bill_items bi JOIN bills b ON bi.bill_id = b.bill_id WHERE b.transaction_datetime::date = %s;", (target_date,))
        units = cursor.fetchone()[0]

        average_bill = revenue / bills if bills else 0

        return {
            "revenue": revenue,
            "bills": bills,
            "units": units,
            "average_bill": average_bill
        }

    finally:
        conn.close()


def get_top_selling_products_for_date(target_date, limit=10):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.product_id, p.product_name, COALESCE(SUM(bi.quantity), 0) AS units_sold FROM bill_items bi JOIN products p ON bi.product_id = p.product_id JOIN bills b ON bi.bill_id = b.bill_id WHERE b.transaction_datetime::date = %s GROUP BY p.product_id, p.product_name ORDER BY units_sold DESC LIMIT %s;", (target_date, limit))
        return cursor.fetchall()
    finally:
        conn.close()


def get_sales_by_category_for_date(target_date):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.category, COALESCE(SUM(bi.line_total), 0) AS sales FROM bill_items bi JOIN products p ON bi.product_id = p.product_id JOIN bills b ON bi.bill_id = b.bill_id WHERE b.transaction_datetime::date = %s GROUP BY p.category ORDER BY sales DESC;", (target_date,))
        return cursor.fetchall()
    finally:
        conn.close()


def get_sales_by_payment_mode_for_date(target_date):
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT payment_mode, COALESCE(SUM(total_amount), 0) AS sales FROM bills WHERE transaction_datetime::date = %s GROUP BY payment_mode ORDER BY sales DESC;", (target_date,))
        return cursor.fetchall()
    finally:
        conn.close()