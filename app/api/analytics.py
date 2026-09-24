from fastapi import APIRouter
from app.Services.analytics_service import *

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/revenue")
def total_revenue():
    return get_total_revenue()

@router.get("/units-sold")
def total_units_sold():
    return get_total_units_sold()

@router.get("/bills")
def total_bills():
    return get_total_bills()

@router.get("/average-bill")
def average_bill():
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