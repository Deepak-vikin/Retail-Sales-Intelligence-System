import re
from datetime import date

from app.gateway.llm_gateway import LLMGateway


class TextToSQL:

    def __init__(self):
        self.gateway = LLMGateway()

    def generate_sql(self, question):

        today = date.today().isoformat()

        prompt = f"""
You are a PostgreSQL Text-to-SQL engine for a retail analytics system.

Your ONLY task is to convert the user's question into ONE valid
PostgreSQL SELECT query.

CURRENT DATE:
{today}

DATABASE SCHEMA:

products(
    product_id,
    barcode,
    product_name,
    category,
    supplier_id,
    cost_price,
    selling_price,
    reorder_level
)

inventory(
    inventory_id,
    product_id,
    current_stock,
    last_updated
)

suppliers(
    supplier_id,
    supplier_name,
    contact_number,
    payment_terms
)

purchases(
    purchase_id,
    product_id,
    supplier_id,
    quantity_received,
    cost_price,
    purchase_date
)

bills(
    bill_id,
    cashier_id,
    transaction_datetime,
    payment_mode,
    total_amount
)

bill_items(
    item_id,
    bill_id,
    product_id,
    quantity,
    unit_price,
    discount,
    line_total
)


============================================================
CRITICAL REVENUE RULES
============================================================

1. bills is the parent table.

2. bill_items is a child table.

3. One bill can contain MULTIPLE bill_items rows.

4. Therefore, NEVER calculate bill-level revenue like this
   after joining bills with bill_items:

   SUM(bills.total_amount)

   because the same bill can be counted multiple times.

5. If bill_items is joined and the question asks for sales/revenue,
   use:

   SUM(bill_items.line_total)

6. If the query uses ONLY bills and does NOT join bill_items,
   bill-level revenue can use:

   SUM(bills.total_amount)

7. For counting bills after joining bill_items, ALWAYS use:

   COUNT(DISTINCT bills.bill_id)

8. For counting products/items sold, use:

   SUM(bill_items.quantity)

9. For revenue by product, use:

   SUM(bill_items.line_total)

10. For revenue by category, use:

   SUM(bill_items.line_total)

11. For revenue by payment mode, if bill_items is not required,
    use:

    SUM(bills.total_amount)

12. If payment mode and product/category information are both
    required, use bill_items.line_total for revenue.

13. Never multiply or duplicate bill-level amounts through
    a one-to-many join.

14. When calculating multiple metrics in a query involving
    bills and bill_items, make sure every metric uses the
    correct aggregation level.


============================================================
GENERAL SQL RULES
============================================================

1. Return exactly ONE PostgreSQL SELECT statement.

2. WITH ... SELECT is allowed.

3. Never generate:
   INSERT
   UPDATE
   DELETE
   DROP
   ALTER
   CREATE
   TRUNCATE
   GRANT
   REVOKE

4. Never generate multiple SQL statements.

5. Never return explanations.

6. Never return Markdown.

7. Never return ```sql.

8. Never describe the query.

9. Use ONLY the tables and columns provided.

10. Use valid PostgreSQL syntax.

11. PostgreSQL must calculate exact numerical values.

12. Do not perform arithmetic manually when PostgreSQL can
    calculate it.

13. Use COALESCE where appropriate.

14. For historical transaction questions, use:

    bills.transaction_datetime

15. For date filtering, prefer:

    bills.transaction_datetime::date = 'YYYY-MM-DD'

16. For a specific date, use the exact date provided by the user.

17. NEVER invent a year.

18. If the user explicitly provides a year, use that year.

19. If the user gives only month and day, do not arbitrarily
    choose an old year such as 2023.

20. For month/day questions without a year, find the relevant
    year from the database when possible.

21. For "today", use:

    CURRENT_DATE

22. For "yesterday", use:

    CURRENT_DATE - INTERVAL '1 day'

23. For "this month", use the current calendar month.

24. For "last month", calculate the previous calendar month.

25. For rankings, use ORDER BY with the appropriate aggregate.

26. For "top selling", aggregate quantity and ORDER BY quantity DESC.

27. For "lowest selling", aggregate quantity and ORDER BY quantity ASC.

28. For counts of bills after joining bill_items, use:

    COUNT(DISTINCT bills.bill_id)

29. For counts of products, use:

    COUNT(DISTINCT products.product_id)

30. For comparisons, calculate both periods explicitly.

31. Never invent data that does not exist in the database.

32. Return SQL ONLY.


============================================================
IMPORTANT BUSINESS SEMANTICS
============================================================

Revenue:
- bills.total_amount = total amount of one complete bill.
- bill_items.line_total = revenue from one individual line item.

Historical transaction price:
- bill_items.unit_price

Current product selling price:
- products.selling_price

Historical purchase cost:
- purchases.cost_price

Current product cost:
- products.cost_price

Inventory:
- inventory.current_stock

Historical transaction date:
- bills.transaction_datetime

Purchase date:
- purchases.purchase_date


============================================================
EXAMPLES
============================================================

Question:
What was the total revenue?

Correct pattern:

SELECT COALESCE(SUM(total_amount), 0) AS total_revenue
FROM bills;


Question:
What was the total revenue by product?

Correct pattern:

SELECT
    p.product_name,
    COALESCE(SUM(bi.line_total), 0) AS revenue
FROM products p
JOIN bill_items bi
    ON p.product_id = bi.product_id
GROUP BY p.product_id, p.product_name
ORDER BY revenue DESC;


Question:
How many bills were there?

Correct pattern:

SELECT COUNT(*) AS total_bills
FROM bills;


Question:
How many bills contained each product?

Correct pattern:

SELECT
    p.product_name,
    COUNT(DISTINCT bi.bill_id) AS bill_count
FROM products p
JOIN bill_items bi
    ON p.product_id = bi.product_id
GROUP BY p.product_id, p.product_name;


Question:
How many units were sold?

Correct pattern:

SELECT COALESCE(SUM(quantity), 0) AS total_units_sold
FROM bill_items;


Question:
What was the revenue on September 30?

Correct pattern:

SELECT
    COALESCE(SUM(total_amount), 0) AS total_revenue
FROM bills
WHERE transaction_datetime::date = 'YYYY-MM-DD';


Question:
What were the sales by category?

Correct pattern:

SELECT
    p.category,
    COALESCE(SUM(bi.line_total), 0) AS sales
FROM products p
JOIN bill_items bi
    ON p.product_id = bi.product_id
GROUP BY p.category
ORDER BY sales DESC;


Question:
What was the sales performance on a date?

A correct query can calculate:

- revenue
- number of bills
- units sold

But remember:

Revenue:
SUM(bills.total_amount)

Bill count:
COUNT(*)

Units:
SUM(bill_items.quantity)

If bills and bill_items are joined, NEVER use
SUM(bills.total_amount) directly.

Instead either:

A. Calculate bill revenue separately,

OR

B. Aggregate bills before joining,

OR

C. Use bill_items.line_total for item-level revenue.


============================================================
DATE SAFETY
============================================================

Current date is:

{today}

If the user asks:

"What was the sales performance on September 30?"

Do NOT automatically use:

2023-09-30

Instead determine the relevant year from the database.

For example, a safe approach is:

WITH target_year AS (
    SELECT EXTRACT(YEAR FROM transaction_datetime) AS year
    FROM bills
    WHERE EXTRACT(MONTH FROM transaction_datetime) = 9
      AND EXTRACT(DAY FROM transaction_datetime) = 30
    ORDER BY transaction_datetime DESC
    LIMIT 1
)

Then use that year for the requested date.


============================================================
USER QUESTION
============================================================

{question}

RETURN ONLY THE SQL QUERY.
"""

        raw_sql = self.gateway.complete(prompt).strip()

        # --------------------------------------------------------
        # Remove Markdown fences
        # --------------------------------------------------------

        raw_sql = re.sub(
            r"```(?:sql)?",
            "",
            raw_sql,
            flags=re.IGNORECASE
        )

        raw_sql = raw_sql.replace("```", "").strip()

        # --------------------------------------------------------
        # Extract SQL
        # --------------------------------------------------------

        match = re.search(
            r"\b(SELECT|WITH)\b",
            raw_sql,
            flags=re.IGNORECASE
        )

        if not match:
            raise ValueError(
                f"LLM did not return SQL:\n{raw_sql}"
            )

        sql = raw_sql[match.start():].strip()

        # --------------------------------------------------------
        # Remove trailing semicolon
        # --------------------------------------------------------

        sql = sql.rstrip(";").strip()

        # --------------------------------------------------------
        # Prevent multiple statements
        # --------------------------------------------------------

        if ";" in sql:
            raise ValueError(
                "Multiple SQL statements detected."
            )

        # --------------------------------------------------------
        # Forbidden SQL operations
        # --------------------------------------------------------

        forbidden = [
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "ALTER",
            "CREATE",
            "TRUNCATE",
            "GRANT",
            "REVOKE"
        ]

        upper_sql = sql.upper()

        for keyword in forbidden:

            if re.search(
                rf"\b{keyword}\b",
                upper_sql
            ):
                raise ValueError(
                    f"Forbidden SQL operation: {keyword}"
                )

        # --------------------------------------------------------
        # Must start with SELECT or WITH
        # --------------------------------------------------------

        if not upper_sql.startswith(
            ("SELECT", "WITH")
        ):
            raise ValueError(
                "Only SELECT queries are allowed."
            )

        return sql + ";"