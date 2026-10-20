from fastapi import APIRouter, Query
from typing import Optional
from app.Services.analytics_service import *
from datetime import date

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# Dedicated today endpoints
@router.get("/today/revenue")
def today_revenue():
    return get_today_revenue()

@router.get("/today/bills")
def today_bills():
    return get_today_bills()

@router.get("/today/units-sold")
def today_units_sold():
    return get_today_units_sold()

@router.get("/today/average-bill")
def today_average_bill():
    return get_today_average_bill_value()

@router.get("/today/comparison")
def today_comparison():
    return get_today_vs_yesterday_comparison()

@router.get("/today/summary")
def today_summary():
    return get_today_summary()

# Dedicated historical total endpoints
@router.get("/total/revenue")
def total_revenue_endpoint():
    return get_total_revenue()

@router.get("/total/bills")
def total_bills_endpoint():
    return get_total_bills()

@router.get("/total/units-sold")
def total_units_sold_endpoint():
    return get_total_units_sold()

@router.get("/total/average-bill")
def total_average_bill_endpoint():
    return get_average_bill_value()

# Routes supporting period query (?period=today or default total)
@router.get("/revenue")
def total_revenue(period: Optional[str] = Query(None)):
    if period == "today":
        return get_today_revenue()
    return get_total_revenue()

@router.get("/units-sold")
def total_units_sold(period: Optional[str] = Query(None)):
    if period == "today":
        return get_today_units_sold()
    return get_total_units_sold()

@router.get("/bills")
def total_bills(period: Optional[str] = Query(None)):
    if period == "today":
        return get_today_bills()
    return get_total_bills()

@router.get("/average-bill")
def average_bill(period: Optional[str] = Query(None)):
    if period == "today":
        return get_today_average_bill_value()
    return get_average_bill_value()

@router.get("/sales/product")
def sales_by_product():
    return get_sales_by_product()

@router.get("/sales/category")
def sales_by_category():
    return get_sales_by_category()

@router.get("/top-products")
def top_products(limit: int = 10):
    return get_top_selling_products(limit)

@router.get("/bottom-products")
def bottom_products(limit: int = 10):
    return get_bottom_selling_products(limit)

@router.get("/sales/payment-mode")
def sales_by_payment_mode():
    return get_sales_by_payment_mode()

@router.get("/sales/daily")
def daily_sales():
    return get_daily_sales()

@router.get("/low-stock-value")
def low_stock_value():
    return get_low_stock_value()

@router.get("/sales/date-range")
def date_range_sales(start_date: date, end_date: date):
    return get_sales_for_date_range(start_date, end_date)
@router.get("/sales/product/{product_id}")
def sales_by_product_id(product_id: int):
    return get_sales_by_product(product_id)
@router.get("/sales/category/{category}")
def sales_by_category(category: str):
    return get_sales_by_category(category)