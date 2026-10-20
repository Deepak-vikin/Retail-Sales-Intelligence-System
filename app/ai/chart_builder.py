"""
chart_builder.py
Converts raw SQL results into structured chart-ready JSON.
All numbers come directly from the database — the LLM never touches these values.
"""

import re
from datetime import date


# ============================================================
# QUESTION-TYPE DETECTOR
# ============================================================

def detect_question_type(question: str) -> str:
    """Returns one of: top_n, trend, comparison, distribution, inventory, simple"""
    q = question.lower()

    if re.search(r"\btop\s*\d+\b|\bbest\s+\d+\b|\bhighest\s+\d+\b|\bworst\s+\d+\b|\blowest\s+\d+\b", q):
        return "top_n"

    if any(w in q for w in ["trend", "over time", "daily", "weekly", "monthly",
                             "last 7", "last 30", "past week", "past month",
                             "last week", "this week", "last month", "this month",
                             "how did", "how has", "performance"]):
        return "trend"

    if any(w in q for w in ["compare", "vs", "versus", "difference between",
                             "better", "worse", "higher", "lower",
                             "which category", "categories", "payment", "mode"]):
        return "comparison"

    if any(w in q for w in ["distribution", "breakdown", "share", "percentage",
                             "proportion", "how are customers paying", "payment mode"]):
        return "distribution"

    if any(w in q for w in ["low stock", "out of stock", "reorder", "below reorder",
                             "low in stock", "running low", "safety stock",
                             "which products are low", "inventory risk"]):
        return "inventory"

    # Single-product stock check → stays simple
    if ("stock" in q or "inventory" in q) and any(
        w in q for w in ["of ", "for ", "current stock", "available"]
    ) and len(q.split()) < 12:
        return "simple"

    if any(w in q for w in ["stock", "inventory"]):
        return "inventory"

    if any(w in q for w in ["top selling", "best selling", "most sold",
                             "top products", "top 5", "top 10"]):
        return "top_n"

    return "simple"


# ============================================================
# MAIN CHART BUILDER
# ============================================================

def build_chart(question: str, sql: str, result: list) -> dict | None:
    """
    Analyse the question + SQL result and produce a chart spec.
    Returns None if no chart is appropriate.
    All values come directly from `result` — never invented.
    """
    if not result:
        return None

    q = question.lower()
    question_type = detect_question_type(question)

    # --------------------------------------------------------
    # TOP N — bar chart: product/category name vs quantity/revenue
    # --------------------------------------------------------
    if question_type == "top_n":
        return _build_top_n_bar(result, question)

    # --------------------------------------------------------
    # TREND — line chart: date vs revenue/units
    # --------------------------------------------------------
    if question_type == "trend":
        return _build_trend_line(result, question)

    # --------------------------------------------------------
    # COMPARISON — bar chart: labels vs values
    # --------------------------------------------------------
    if question_type == "comparison":
        return _build_comparison_bar(result, question)

    # --------------------------------------------------------
    # DISTRIBUTION (payment, category share) — bar chart
    # --------------------------------------------------------
    if question_type == "distribution":
        return _build_distribution_bar(result, question)

    # --------------------------------------------------------
    # INVENTORY — bar chart: product vs current_stock/reorder
    # --------------------------------------------------------
    if question_type == "inventory":
        return _build_inventory_bar(result)

    # --------------------------------------------------------
    # Simple multi-row results — try a bar if sensible
    # --------------------------------------------------------
    if len(result) > 3 and len(result[0]) >= 2:
        return _build_generic_bar(result, question)

    return None


# ============================================================
# CHART BUILDERS
# ============================================================

def _build_top_n_bar(result: list, question: str) -> dict:
    """Ranked product/category bar chart."""
    labels, values, y_label = [], [], "Value"

    revenue_keywords = ["revenue", "sales", "amount", "income"]
    unit_keywords = ["unit", "quantity", "sold", "items"]
    q = question.lower()

    for row in result:
        # Expect: (id_or_name, name_or_value, value_or_extra...)
        if len(row) >= 3:
            label = str(row[1])
            value = _safe_float(row[2])
        elif len(row) == 2:
            label = str(row[0])
            value = _safe_float(row[1])
        else:
            continue
        labels.append(label)
        values.append(value)

    if any(k in q for k in revenue_keywords):
        y_label = "Revenue (₹)"
        title = "Revenue by Product / Category"
    elif any(k in q for k in unit_keywords):
        y_label = "Units Sold"
        title = "Units Sold by Product"
    else:
        y_label = "Value"
        title = "Performance Ranking"

    return {
        "chart_type": "bar",
        "title": title,
        "x_axis": "Product / Category",
        "y_axis": y_label,
        "data": [{"label": l, "value": v} for l, v in zip(labels, values)],
    }


def _build_trend_line(result: list, question: str) -> dict:
    """Daily/weekly revenue or unit trend line chart."""
    points = []
    revenue_keywords = ["revenue", "sales", "amount"]
    q = question.lower()

    for row in result:
        if len(row) >= 2:
            date_val = _format_date_label(row[0])
            value = _safe_float(row[1])
            points.append({"date": date_val, "value": value})

    y_label = "Revenue (₹)" if any(k in q for k in revenue_keywords) else "Value"
    title = "Sales Trend Over Time" if any(k in q for k in revenue_keywords) else "Trend Over Time"

    return {
        "chart_type": "line",
        "title": title,
        "x_axis": "Date",
        "y_axis": y_label,
        "data": points,
    }


def _build_comparison_bar(result: list, question: str) -> dict:
    """Side-by-side or single comparison bar."""
    labels, values = [], []

    for row in result:
        if len(row) >= 2:
            label = str(row[0])
            value = _safe_float(row[1])
            labels.append(label)
            values.append(value)

    return {
        "chart_type": "bar",
        "title": "Comparison",
        "x_axis": "Category",
        "y_axis": "Revenue (₹)",
        "data": [{"label": l, "value": v} for l, v in zip(labels, values)],
    }


def _build_distribution_bar(result: list, question: str) -> dict:
    """Payment mode / category distribution bar."""
    labels, values = [], []
    total = 0

    for row in result:
        if len(row) >= 2:
            label = str(row[0])
            value = _safe_float(row[1])
            labels.append(label)
            values.append(value)
            total += value

    data = []
    for l, v in zip(labels, values):
        pct = round((v / total * 100), 1) if total > 0 else 0
        data.append({"label": l, "value": v, "percentage": pct})

    return {
        "chart_type": "bar",
        "title": "Distribution",
        "x_axis": "Category / Mode",
        "y_axis": "Revenue (₹)",
        "data": data,
    }


def _build_inventory_bar(result: list) -> dict:
    """Current stock vs reorder level bar chart."""
    data = []

    for row in result:
        # Expect rows to contain at least: name, stock, reorder
        # Row shape from low_stock query: (inv_id, name, ..., stock, reorder, ...)
        if len(row) >= 5:
            name = str(row[1])
            stock = _safe_float(row[4] if len(row) > 4 else row[2])
            reorder = _safe_float(row[5] if len(row) > 5 else row[3])
        elif len(row) == 4:
            name = str(row[0])
            stock = _safe_float(row[2])
            reorder = _safe_float(row[3])
        elif len(row) == 3:
            name = str(row[0])
            stock = _safe_float(row[1])
            reorder = _safe_float(row[2])
        else:
            continue
        data.append({"label": name, "stock": stock, "reorder": reorder})

    return {
        "chart_type": "inventory_bar",
        "title": "Stock vs Reorder Level",
        "x_axis": "Product",
        "y_axis": "Units",
        "data": data,
    }


def _build_generic_bar(result: list, question: str) -> dict:
    """Fallback bar for multi-row results."""
    labels, values = [], []

    for row in result:
        if len(row) >= 3:
            labels.append(str(row[1]))
            values.append(_safe_float(row[2]))
        elif len(row) == 2:
            labels.append(str(row[0]))
            values.append(_safe_float(row[1]))

    if not labels:
        return None

    return {
        "chart_type": "bar",
        "title": "Analysis",
        "x_axis": "Category",
        "y_axis": "Value",
        "data": [{"label": l, "value": v} for l, v in zip(labels, values)],
    }


# ============================================================
# HELPERS
# ============================================================

def _safe_float(val) -> float:
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _format_date_label(val) -> str:
    if val is None:
        return "—"
    if hasattr(val, "strftime"):
        return val.strftime("%b %d")
    s = str(val)
    # Try to parse YYYY-MM-DD
    try:
        d = date.fromisoformat(s[:10])
        return d.strftime("%b %d")
    except ValueError:
        return s


# ============================================================
# FOLLOW-UP SUGGESTION GENERATOR
# ============================================================

def suggest_follow_ups(question: str, result: list) -> list[str]:
    """Returns 2-3 relevant follow-up questions."""
    q = question.lower()
    suggestions = []

    if "top" in q and "product" in q:
        suggestions = [
            "Which category generates the most revenue?",
            "Show me the revenue trend for this week",
            "Which products are low in stock?",
        ]
    elif "revenue" in q and ("today" in q or "yesterday" in q or "week" in q):
        suggestions = [
            "Which category contributed most?",
            "What are our top 5 selling products?",
            "Compare this with last month",
        ]
    elif "category" in q:
        suggestions = [
            "What are the top products in the best category?",
            "Show me the revenue trend over the last 7 days",
            "Which products are running low?",
        ]
    elif "stock" in q or "inventory" in q or "reorder" in q:
        suggestions = [
            "Which supplier provides the most products?",
            "What was our total stock received this month?",
            "Which product has the highest sales?",
        ]
    elif "payment" in q:
        suggestions = [
            "What is our total revenue?",
            "Show me sales by category",
            "What are our top 5 selling products?",
        ]
    elif "bill" in q:
        suggestions = [
            "What is today's revenue?",
            "What are our top selling products?",
            "Show me daily sales for this week",
        ]
    else:
        suggestions = [
            "What are our top 5 selling products?",
            "Which category performs best?",
            "How are customers paying?",
        ]

    return suggestions[:3]
