import re

from app.gateway.llm_gateway import LLMGateway


class QueryRouter:

    def __init__(self):
        self.gateway = LLMGateway()

    def route(self, question: str) -> str:

        q = question.lower().strip()

        # =========================================================
        # HYBRID
        # =========================================================

        explanation_patterns = [
            r"\bwhy\b",
            r"\bwhy did\b",
            r"\bwhy is\b",
            r"\bwhy are\b",
            r"\bwhat caused\b",
            r"\bwhat is causing\b",
            r"\bexplain\b",
            r"\breason for\b",
            r"\bwhat happened\b",
            r"\bwhat led to\b",
        ]

        database_terms = [
            "revenue",
            "sales",
            "bill",
            "bills",
            "product",
            "products",
            "inventory",
            "stock",
            "units",
            "quantity",
            "purchase",
            "purchases",
            "payment",
            "category",
            "categories",
            "cashier",
            "transaction",
        ]

        has_explanation = any(
            re.search(pattern, q)
            for pattern in explanation_patterns
        )

        has_database_term = any(
            term in q
            for term in database_terms
        )

        if has_explanation and has_database_term:
            return "HYBRID"

        # =========================================================
        # RAG
        # =========================================================

        rag_patterns = [
            r"\bpolicy\b",
            r"\bpolicies\b",
            r"\bprocedure\b",
            r"\bprocedures\b",
            r"\bworkflow\b",
            r"\bstore rules\b",
            r"\bbusiness rules\b",
            r"\breturn policy\b",
            r"\brefund policy\b",
            r"\bbilling procedure\b",
            r"\bstore procedure\b",
            r"\bstore process\b",
            r"\bhow does the store operate\b",
            r"\bhow do we operate\b",
            r"\boperational process\b",
        ]

        if any(
            re.search(pattern, q)
            for pattern in rag_patterns
        ):
            return "RAG"

        # =========================================================
        # SQL
        # =========================================================

        sql_patterns = [
            r"\bhow many\b",
            r"\bhow much\b",
            r"\btotal\b",
            r"\brevenue\b",
            r"\bsales\b",
            r"\bsold\b",
            r"\bselling\b",
            r"\btop selling\b",
            r"\bbest selling\b",
            r"\blowest selling\b",
            r"\bworst selling\b",
            r"\bunits sold\b",
            r"\bquantity\b",
            r"\bcount\b",
            r"\baverage\b",
            r"\bhighest\b",
            r"\blowest\b",
            r"\bmaximum\b",
            r"\bminimum\b",
            r"\brank\b",
            r"\branking\b",
            r"\binventory\b",
            r"\bstock\b",
            r"\blow stock\b",
            r"\bproduct\b",
            r"\bproducts\b",
            r"\bsupplier\b",
            r"\bsuppliers\b",
            r"\bpurchase\b",
            r"\bpurchases\b",
            r"\bbill\b",
            r"\bbills\b",
            r"\btransaction\b",
            r"\btransactions\b",
            r"\bpayment\b",
            r"\bcategory\b",
            r"\bcategories\b",
            r"\btoday\b",
            r"\byesterday\b",
            r"\btomorrow\b",
            r"\bthis week\b",
            r"\blast week\b",
            r"\bthis month\b",
            r"\blast month\b",
            r"\bdate\b",
        ]

        if any(
            re.search(pattern, q)
            for pattern in sql_patterns
        ):
            return "SQL"

        # =========================================================
        # LLM FALLBACK
        # =========================================================

        return self._llm_route(question)

    def _llm_route(self, question: str) -> str:

        prompt = f"""
You are the query router for a retail intelligence system.

Classify the user's question into exactly ONE route.

SQL:
Use SQL when PostgreSQL contains the authoritative answer.

Examples:
- total revenue
- revenue on a date
- sales
- number of bills
- units sold
- top selling products
- lowest selling products
- inventory
- stock
- suppliers
- purchases
- payment modes
- categories
- transaction counts

RAG:
Use RAG when the question asks about business knowledge,
policies, procedures, workflows, or operational information
that is not an exact PostgreSQL calculation.

Examples:
- What is the return policy?
- What is the billing procedure?
- How does the store operate?

HYBRID:
Use HYBRID when BOTH PostgreSQL data and contextual knowledge
are required.

Examples:
- Why did revenue increase?
- Why did sales decrease?
- Explain today's sales performance.
- Why is a product performing poorly?
- What caused the inventory problem?

IMPORTANT:

Return exactly ONE word:

SQL
RAG
HYBRID

Do not return JSON.
Do not return Markdown.
Do not explain your decision.

USER QUESTION:
{question}
"""

        try:

            result = self.gateway.complete(prompt)

            result = result.strip().upper()

            if result in {
                "SQL",
                "RAG",
                "HYBRID"
            }:
                return result

            matches = re.findall(
                r"\b(SQL|RAG|HYBRID)\b",
                result
            )

            if "HYBRID" in matches:
                return "HYBRID"

            if "SQL" in matches:
                return "SQL"

            if "RAG" in matches:
                return "RAG"

        except Exception:
            pass

        # Safest default for unknown questions.
        return "RAG"