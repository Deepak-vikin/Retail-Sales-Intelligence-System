from datetime import date, timedelta

from app.ai.query_router import QueryRouter
from app.ai.text_to_sql import TextToSQL
from app.ai.sql_connector import execute_sql
from app.ai.answer_generator import AnswerGenerator
from app.ai.chart_builder import build_chart, detect_question_type, suggest_follow_ups

from app.rag.vector_store import search_documents
from app.rag.rag_answer_generator import RAGAnswerGenerator


class QueryEngine:

    def __init__(self):
        self.router = QueryRouter()
        self.text_to_sql = TextToSQL()

        self.sql_answer_generator = AnswerGenerator()
        self.rag_answer_generator = RAGAnswerGenerator()

    # ============================================================
    # MAIN ENTRY POINT
    # ============================================================

    def ask(self, question):

        route = self.router.route(question)

        print("ROUTE:", route)

        if route == "SQL":
            return self._handle_sql(question)

        if route == "RAG":
            return self._handle_rag(question)

        if route == "HYBRID":
            return self._handle_hybrid(question)

        raise ValueError(
            f"Unknown route: {route}"
        )

    # ============================================================
    # SQL
    # ============================================================

    def _handle_sql(self, question):

        sql = self.text_to_sql.generate_sql(question)

        print("GENERATED SQL:", sql)

        result = execute_sql(sql)

        # Detect question complexity for adaptive response depth
        question_type = detect_question_type(question)

        answer = self.sql_answer_generator.generate_answer(
            question,
            sql,
            result,
            question_type=question_type,
        )

        # Build chart from real SQL results — LLM does NOT touch these numbers
        chart = build_chart(question, sql, result)

        # Suggest follow-ups based on question type and data
        follow_ups = suggest_follow_ups(question, result)

        return {
            "route": "SQL",
            "question": question,
            "question_type": question_type,
            "sql": sql,
            "result": result,
            "answer": answer,
            "chart": chart,
            "follow_ups": follow_ups,
        }

    # ============================================================
    # RAG
    # ============================================================

    def _handle_rag(self, question):

        documents = search_documents(
            question,
            limit=5
        )

        answer = self.rag_answer_generator.generate_answer(
            question,
            documents
        )

        return {
            "route": "RAG",
            "question": question,
            "documents": documents,
            "answer": answer
        }

    # ============================================================
    # HYBRID
    # ============================================================

    def _handle_hybrid(self, question):

        # --------------------------------------------------------
        # 1. Determine comparison dates
        # --------------------------------------------------------

        current_date, previous_date = self._resolve_comparison_dates(
            question
        )

        # --------------------------------------------------------
        # 2. Get exact SQL metrics
        # --------------------------------------------------------

        metrics_sql = f"""
SELECT
    COALESCE(SUM(
        CASE
            WHEN transaction_datetime::date = '{current_date}'
            THEN total_amount
            ELSE 0
        END
    ), 0) AS current_revenue,

    COALESCE(SUM(
        CASE
            WHEN transaction_datetime::date = '{previous_date}'
            THEN total_amount
            ELSE 0
        END
    ), 0) AS previous_revenue,

    COUNT(
        CASE
            WHEN transaction_datetime::date = '{current_date}'
            THEN 1
        END
    ) AS current_bills,

    COUNT(
        CASE
            WHEN transaction_datetime::date = '{previous_date}'
            THEN 1
        END
    ) AS previous_bills

FROM bills;
""".strip()

        print("HYBRID METRICS SQL:", metrics_sql)

        metrics_result = execute_sql(
            metrics_sql
        )

        # --------------------------------------------------------
        # 3. Calculate revenue change
        # --------------------------------------------------------

        if metrics_result:

            row = metrics_result[0]

            current_revenue = float(
                row[0] or 0
            )

            previous_revenue = float(
                row[1] or 0
            )

            current_bills = int(
                row[2] or 0
            )

            previous_bills = int(
                row[3] or 0
            )

        else:

            current_revenue = 0
            previous_revenue = 0
            current_bills = 0
            previous_bills = 0

        revenue_change = (
            current_revenue -
            previous_revenue
        )

        if previous_revenue != 0:

            revenue_change_percent = (
                revenue_change /
                previous_revenue
            ) * 100

        else:

            revenue_change_percent = None

        # --------------------------------------------------------
        # 4. Find products contributing to the change
        # --------------------------------------------------------

        product_sql = f"""
SELECT
    p.product_name,
    p.category,

    COALESCE(SUM(
        CASE
            WHEN b.transaction_datetime::date = '{current_date}'
            THEN bi.line_total
            ELSE 0
        END
    ), 0) AS current_sales,

    COALESCE(SUM(
        CASE
            WHEN b.transaction_datetime::date = '{previous_date}'
            THEN bi.line_total
            ELSE 0
        END
    ), 0) AS previous_sales,

    COALESCE(SUM(
        CASE
            WHEN b.transaction_datetime::date = '{current_date}'
            THEN bi.line_total
            ELSE 0
        END
    ), 0)
    -
    COALESCE(SUM(
        CASE
            WHEN b.transaction_datetime::date = '{previous_date}'
            THEN bi.line_total
            ELSE 0
        END
    ), 0) AS sales_change

FROM products p

JOIN bill_items bi
    ON p.product_id = bi.product_id

JOIN bills b
    ON bi.bill_id = b.bill_id

WHERE b.transaction_datetime::date
      IN ('{current_date}', '{previous_date}')

GROUP BY
    p.product_id,
    p.product_name,
    p.category

ORDER BY sales_change DESC

LIMIT 10;
""".strip()

        print("HYBRID PRODUCT SQL:", product_sql)

        product_result = execute_sql(
            product_sql
        )

        # --------------------------------------------------------
        # 5. Category contribution
        # --------------------------------------------------------

        category_sql = f"""
SELECT
    p.category,

    COALESCE(SUM(
        CASE
            WHEN b.transaction_datetime::date = '{current_date}'
            THEN bi.line_total
            ELSE 0
        END
    ), 0) AS current_sales,

    COALESCE(SUM(
        CASE
            WHEN b.transaction_datetime::date = '{previous_date}'
            THEN bi.line_total
            ELSE 0
        END
    ), 0) AS previous_sales,

    COALESCE(SUM(
        CASE
            WHEN b.transaction_datetime::date = '{current_date}'
            THEN bi.line_total
            ELSE 0
        END
    ), 0)
    -
    COALESCE(SUM(
        CASE
            WHEN b.transaction_datetime::date = '{previous_date}'
            THEN bi.line_total
            ELSE 0
        END
    ), 0) AS sales_change

FROM products p

JOIN bill_items bi
    ON p.product_id = bi.product_id

JOIN bills b
    ON bi.bill_id = b.bill_id

WHERE b.transaction_datetime::date
      IN ('{current_date}', '{previous_date}')

GROUP BY
    p.category

ORDER BY sales_change DESC;
""".strip()

        print("HYBRID CATEGORY SQL:", category_sql)

        category_result = execute_sql(
            category_sql
        )

        # --------------------------------------------------------
        # 6. Retrieve RAG context
        # --------------------------------------------------------

        documents = search_documents(
            question,
            limit=5
        )

        context = "\n\n".join(
            document[0]
            for document in documents
        )

        # --------------------------------------------------------
        # 7. Build controlled evidence
        # --------------------------------------------------------

        evidence = {
            "current_date": str(current_date),
            "previous_date": str(previous_date),

            "current_revenue": current_revenue,
            "previous_revenue": previous_revenue,

            "revenue_change": revenue_change,
            "revenue_change_percent": revenue_change_percent,

            "current_bills": current_bills,
            "previous_bills": previous_bills,

            "top_product_changes": product_result,
            "category_changes": category_result
        }

        # --------------------------------------------------------
        # 8. Generate final explanation
        # --------------------------------------------------------

        prompt = f"""You are an expert AI Retail Business Analyst for an Indian retail store.

USER QUESTION:
{question}

EXACT DATABASE EVIDENCE (authoritative numbers — do not change them):
{evidence}

RETRIEVED BUSINESS KNOWLEDGE:
{context}

STRICT RULES:
1. Database values are authoritative. Never change, round, or invent numbers.
2. Monetary values are Indian Rupees (₹). Never use $ or USD.
3. Do not claim a cause unless the evidence actually supports it.
4. If evidence shows correlation only, say "contributed to" not "caused".
5. If the retrieved knowledge does not explain the cause, explicitly say so.
6. Never invent products, dates, or percentages not in the evidence.

RESPONSE FORMAT (Markdown, rendered by frontend):

## [Descriptive Title]

**[One-sentence key finding]**

### Comparison Overview

| Metric | {evidence.get('previous_date', 'Previous')} | {evidence.get('current_date', 'Current')} | Change |
|--------|-----------|---------|--------|
| Revenue | ₹X | ₹Y | ±Z% |
| Bills | N | M | ±Z% |

(Fill in from the evidence values above)

### Top Contributors

List the products/categories that contributed most to the change,
using ONLY the top_product_changes and category_changes from the evidence.

### Analysis

Interpret what the numbers mean in a business context.

### Insights

2-4 bullet points derived only from the data.

### Recommendation *(only if the data clearly supports one)*

Practical, specific action.

Write the response now. Use Markdown.
"""

        answer = self.sql_answer_generator.gateway.complete(
            prompt
        ).strip()

        # Build a category trend chart from the product change data if available
        chart_data = []
        if product_result:
            for row in product_result[:10]:
                if len(row) >= 5:
                    chart_data.append({"label": str(row[0]), "value": float(row[2] or 0)})

        chart = None
        if chart_data:
            chart = {
                "chart_type": "bar",
                "title": f"Revenue Comparison: {evidence.get('previous_date')} vs {evidence.get('current_date')}",
                "x_axis": "Product",
                "y_axis": "Revenue (₹)",
                "data": chart_data,
            }

        follow_ups = suggest_follow_ups(question, product_result or [])

        # --------------------------------------------------------
        # 9. Return complete HYBRID response
        # --------------------------------------------------------

        return {
            "route": "HYBRID",
            "question": question,

            "comparison": {
                "current_date": str(current_date),
                "previous_date": str(previous_date)
            },

            "metrics_sql": metrics_sql,
            "metrics_result": metrics_result,

            "product_sql": product_sql,
            "product_result": product_result,

            "category_sql": category_sql,
            "category_result": category_result,

            "documents": documents,

            "answer": answer,
            "chart": chart,
            "follow_ups": follow_ups,
        }


    # ============================================================
    # DATE RESOLUTION
    # ============================================================

    def _resolve_comparison_dates(self, question):

        q = question.lower()

        today = date.today()

        # --------------------------------------------------------
        # Explicit September 30 / similar date
        # --------------------------------------------------------

        months = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12
        }

        import re

        match = re.search(
            r"\b("
            + "|".join(months.keys())
            + r")\s+(\d{1,2})(?:,\s*(\d{4}))?\b",
            q
        )

        if match:

            month_name = match.group(1)
            day = int(match.group(2))
            year = match.group(3)

            if year:

                year = int(year)

            else:

                year = today.year

            current_date = date(
                year,
                months[month_name],
                day
            )

            previous_date = (
                current_date -
                timedelta(days=1)
            )

            return current_date, previous_date

        # --------------------------------------------------------
        # Today
        # --------------------------------------------------------

        if "today" in q:

            return (
                today,
                today - timedelta(days=1)
            )

        # --------------------------------------------------------
        # Yesterday
        # --------------------------------------------------------

        if "yesterday" in q:

            yesterday = (
                today -
                timedelta(days=1)
            )

            return (
                yesterday,
                yesterday - timedelta(days=1)
            )

        # --------------------------------------------------------
        # Default
        # --------------------------------------------------------

        return (
            today,
            today - timedelta(days=1)
        )