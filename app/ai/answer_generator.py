"""
answer_generator.py — AI Retail Business Analyst

Transforms raw SQL results into rich, structured Markdown analysis
with contextual business interpretation. The LLM only writes narrative;
all numbers are passed in from the database.
"""

import json
from app.gateway.llm_gateway import LLMGateway


class AnswerGenerator:

    def __init__(self):
        self.gateway = LLMGateway()

    def generate_answer(
        self,
        question: str,
        sql: str,
        result: list,
        question_type: str = "simple",
    ) -> str:
        """
        Generate a rich, analyst-level Markdown response.
        question_type: simple | top_n | trend | comparison | distribution | inventory
        """

        # Serialize result safely — cap at 50 rows to stay within token budget
        result_preview = self._serialize_result(result, max_rows=50)

        depth_guide = self._depth_guide(question_type)

        prompt = f"""You are an expert AI Retail Business Analyst for an Indian retail store.

USER QUESTION:
{question}

SQL EXECUTED (for reference):
{sql}

DATABASE RESULT (exact values — do NOT change these):
{result_preview}

QUESTION TYPE: {question_type}

{depth_guide}

============================================================
STRICT RULES — NEVER BREAK THESE
============================================================

1. Every single number in your response MUST come from the DATABASE RESULT above.
   Never invent, round up, or fabricate a number.

2. Currency is Indian Rupees. Format as ₹X,XX,XXX or ₹X.XXL for readability.
   Use ₹ symbol ALWAYS. Never use $ or USD.

3. If the result is empty or all zeros, state clearly:
   "There are no recorded transactions for this period."
   Do not fabricate positive trends.

4. Never mention SQL, database, or internal system details.

5. For "today" queries that return 0: clearly say 0 and do not
   substitute historical totals.

6. If data is insufficient to establish a cause, explicitly state:
   "The available data shows X but does not establish the exact cause."

============================================================
RESPONSE FORMAT — MANDATORY
============================================================

Use proper Markdown. The frontend renders it.

Structure (adapt depth to question complexity):

## [Descriptive Title]

**[Key finding in one sentence]**

### Key Metrics

Use a table OR bullet list of the main numbers from the result.

### Analysis

Interpret what the numbers mean in a retail business context:
- What is the pattern?
- What stands out?
- What is the magnitude?

### Insights

2-4 bullet points of concrete business insights derived ONLY from the data.

### Recommendation *(include only when the data clearly supports one)*

A practical, specific action the store can take.

============================================================
DEPTH GUIDE FOR THIS QUESTION TYPE
============================================================
{depth_guide}

Write the response now. Use Markdown. Do not add preamble or meta-commentary.
"""

        return self.gateway.complete(prompt).strip()

    # ============================================================
    # DEPTH GUIDES BY QUESTION TYPE
    # ============================================================

    def _depth_guide(self, question_type: str) -> str:
        guides = {
            "simple": """
DEPTH: CONCISE (2-4 short paragraphs)
- State the answer directly.
- Add 1-2 sentences of context.
- Skip elaborate headers for very simple answers.
""",
            "top_n": """
DEPTH: DETAILED
- Show the full ranked list (use a Markdown table with Rank, Product, Value columns).
- Identify the leader and the gap to #2.
- Note which category dominates.
- Call out any surprising entry.
- A bar chart will be rendered automatically from the data.
""",
            "trend": """
DEPTH: ANALYTICAL
- Show the actual data points (table: Date | Revenue/Units).
- Identify the highest and lowest values with their dates.
- Calculate and state average daily value.
- Describe the direction (growing / declining / volatile).
- Highlight any notable spikes or drops.
- A line chart will be rendered automatically from the data.
""",
            "comparison": """
DEPTH: COMPARATIVE
- Present the comparison clearly (table if 3+ items, else inline).
- State which side wins and by how much (absolute + percentage).
- Explain what the difference means in business terms.
- A bar chart will be rendered from the data.
""",
            "distribution": """
DEPTH: ANALYTICAL
- Show each segment's value AND percentage of total.
- Identify the dominant segment.
- Note any underperforming segments.
- A bar/distribution chart will be rendered from the data.
""",
            "inventory": """
DEPTH: OPERATIONAL
- Group products: critically low (≤ 50% of reorder), moderately low (51-100% of reorder).
- State which require IMMEDIATE attention.
- Calculate the total stock gap.
- An inventory comparison chart will be rendered.
""",
        }
        return guides.get(question_type, guides["simple"])

    # ============================================================
    # RESULT SERIALIZER
    # ============================================================

    def _serialize_result(self, result: list, max_rows: int = 50) -> str:
        if not result:
            return "[]  (empty — no records found)"

        rows = result[:max_rows]
        lines = []
        for i, row in enumerate(rows):
            # Convert Decimal/date/datetime to plain types
            clean = [self._clean_val(v) for v in row]
            lines.append(f"  Row {i+1}: {clean}")

        suffix = f"\n  ... ({len(result) - max_rows} more rows truncated)" if len(result) > max_rows else ""
        return "[\n" + "\n".join(lines) + "\n]" + suffix

    @staticmethod
    def _clean_val(v):
        """Convert Decimal/date/datetime to JSON-serializable types."""
        if v is None:
            return None
        try:
            import decimal
            if isinstance(v, decimal.Decimal):
                return float(v)
        except ImportError:
            pass
        try:
            import datetime
            if isinstance(v, (datetime.date, datetime.datetime)):
                return str(v)
        except ImportError:
            pass
        return v