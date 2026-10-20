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

RULES:

1. Return exactly ONE PostgreSQL SELECT statement.

2. WITH ... SELECT is allowed.

3. Never generate INSERT, UPDATE, DELETE, DROP, ALTER,
   CREATE, TRUNCATE, GRANT, or REVOKE.

4. Never generate multiple SQL statements.

5. Never return explanations.

6. Never return Markdown.

7. Never return ```sql.

8. Never describe the query.

9. Use only the tables and columns provided.

10. Use PostgreSQL syntax.

11. PostgreSQL must calculate exact numerical values.

12. For historical sales/revenue at item level,
    use bill_items.line_total.

13. For bill-level revenue,
    use bills.total_amount.

14. For historical transactions,
    use bills.transaction_datetime.

15. For top-selling products,
    aggregate bill_items.quantity and ORDER BY quantity DESC.

16. For lowest-selling products,
    aggregate bill_items.quantity and ORDER BY quantity ASC.

17. For a specific date, use that date.

18. NEVER invent a year.

19. If the user provides a complete date including year,
    use the exact year.

20. If the user provides only month and day,
    determine the year from the available database data.
    Do not arbitrarily use 2023, 2024, 2025, or another year.

21. For "today" or "today's":
    ALWAYS filter transactions to the current date using:
    transaction_datetime::date = CURRENT_DATE
    - Today's Bills:
      SELECT COUNT(*) FROM bills WHERE transaction_datetime::date = CURRENT_DATE;
      (CRITICAL: NEVER use SELECT COUNT(*) FROM bills; for today's bills!)
    - Today's Sales / Revenue:
      SELECT COALESCE(SUM(total_amount), 0) FROM bills WHERE transaction_datetime::date = CURRENT_DATE;
    - Today's Units Sold:
      SELECT COALESCE(SUM(bi.quantity), 0) FROM bills b JOIN bill_items bi ON b.bill_id = bi.bill_id WHERE b.transaction_datetime::date = CURRENT_DATE;
    - Today's Average Bill Value:
      SELECT CASE WHEN COUNT(*) > 0 THEN COALESCE(SUM(total_amount), 0) / COUNT(*) ELSE 0 END FROM bills WHERE transaction_datetime::date = CURRENT_DATE;

22. For "yesterday":
    Use: transaction_datetime::date = CURRENT_DATE - INTERVAL '1 day'

23. For "tomorrow":
    Use: transaction_datetime::date = CURRENT_DATE + INTERVAL '1 day'

24. For "this week":
    Use: date_trunc('week', transaction_datetime) = date_trunc('week', CURRENT_DATE::timestamp)

25. For "last week":
    Use: date_trunc('week', transaction_datetime) = date_trunc('week', CURRENT_DATE::timestamp) - INTERVAL '1 week'

26. For "this month":
    Use: date_trunc('month', transaction_datetime) = date_trunc('month', CURRENT_DATE::timestamp)

27. For "last month":
    Use: date_trunc('month', transaction_datetime) = date_trunc('month', CURRENT_DATE::timestamp) - INTERVAL '1 month'

28. TOTAL / LIFETIME HISTORICAL QUERIES:
    When the user asks for total, lifetime, or all records in the database
    (e.g., "How many total bills are in the database?", "total bills count", "total revenue overall"),
    do NOT filter by date.
    Use: SELECT COUNT(*) FROM bills;
    or: SELECT COALESCE(SUM(total_amount), 0) FROM bills;
    NEVER confuse total historical queries with today queries.

29. For comparisons, calculate the requested periods explicitly.

30. Never use a hardcoded year unless the user explicitly provided it.

31. Return only SQL.

USER QUESTION:
{question}
"""

        raw_sql = self.gateway.complete(prompt).strip()

        # Remove Markdown fences if model ignores the instruction.
        raw_sql = re.sub(
            r"```(?:sql)?",
            "",
            raw_sql,
            flags=re.IGNORECASE
        )

        raw_sql = raw_sql.replace("```", "").strip()

        # Find SELECT or WITH.
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

        # Remove trailing semicolon.
        sql = sql.rstrip(";").strip()

        # Prevent multiple statements.
        if ";" in sql:
            raise ValueError(
                "Multiple SQL statements detected."
            )

        # Basic safety check.
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

        if not upper_sql.startswith(
            ("SELECT", "WITH")
        ):
            raise ValueError(
                "Only SELECT queries are allowed."
            )

        return sql + ";"