
from datetime import date

from app.Services.analytics_service import (
    get_daily_sales_for_date,
    get_top_selling_products_for_date,
    get_sales_by_category_for_date,
    get_sales_by_payment_mode_for_date,
)
from app.Services.inventory_service import (
    get_low_stock_products,
    get_out_of_stock_products,
)
from app.Services.purchase_service import (
    get_purchases_for_date,
)
from app.rag.vector_store import upsert_document


def generate_daily_knowledge(target_date=None):
    if target_date is None:
        target_date = date.today()

    daily = get_daily_sales_for_date(target_date)
    top_products = get_top_selling_products_for_date(target_date)
    categories = get_sales_by_category_for_date(target_date)
    payment_modes = get_sales_by_payment_mode_for_date(target_date)
    purchases = get_purchases_for_date(target_date)

    document = f"""
Daily Retail Intelligence Summary

Date: {target_date}

SALES PERFORMANCE

Revenue: ₹{daily["revenue"]}
Bills: {daily["bills"]}
Units sold: {daily["units"]}
Average bill value: ₹{daily["average_bill"]}

TOP SELLING PRODUCTS

{top_products}

CATEGORY SALES

{categories}

PAYMENT MODE SALES

{payment_modes}

STOCK RECEIVED

{purchases}

INVENTORY STATUS

Low-stock products:
{get_low_stock_products()}

Out-of-stock products:
{get_out_of_stock_products()}
""".strip()

    return document


def refresh_daily_knowledge(target_date=None):
    if target_date is None:
        target_date = date.today()

    content = generate_daily_knowledge(target_date)

    return upsert_document(
        content=content,
        metadata={
            "type": "daily_summary",
            "date": str(target_date),
        },
    )
