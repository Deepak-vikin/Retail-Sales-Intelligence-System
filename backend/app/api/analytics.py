from fastapi import APIRouter, Query, Depends
from typing import Optional
from app.Services.analytics_service import *
from datetime import date
from app.core.auth import require_permission
from app.core.permissions import Permission, UserContext

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/today/revenue")
def today_revenue(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_today_revenue()

@router.get("/today/bills")
def today_bills(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_today_bills()

@router.get("/today/units-sold")
def today_units_sold(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_today_units_sold()

@router.get("/today/average-bill")
def today_average_bill(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_today_average_bill_value()

@router.get("/today/comparison")
def today_comparison(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_today_vs_yesterday_comparison()

@router.get("/today/summary")
def today_summary(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_today_summary()

@router.get("/total/revenue")
def total_revenue_endpoint(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_total_revenue()

@router.get("/total/bills")
def total_bills_endpoint(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_total_bills()

@router.get("/total/units-sold")
def total_units_sold_endpoint(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_total_units_sold()

@router.get("/total/average-bill")
def total_average_bill_endpoint(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_average_bill_value()

@router.get("/revenue")
def revenue_by_date_range(start_date: date, end_date: date, user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_revenue_by_date_range(start_date, end_date)

@router.get("/sales/daily")
def daily_sales_trend(days: int = 7, user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_daily_sales_trend(days)

@router.get("/sales/monthly")
def monthly_sales_trend(year: Optional[int] = None, user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_monthly_sales_trend(year)

@router.get("/top-products")
def top_products(limit: int = 5, user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_top_selling_products(limit)

@router.get("/top-categories")
def top_categories(limit: int = 5, user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_top_categories(limit)

@router.get("/slow-moving-products")
def slow_moving_products(days: int = 30, limit: int = 10, user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_slow_moving_products(days, limit)

@router.get("/sales/hourly")
def peak_sales_hours(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_peak_sales_hours()

@router.get("/sales/day-of-week")
def peak_sales_days(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_peak_sales_days()

@router.get("/sales/payment-modes")
def sales_by_payment_mode(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_sales_by_payment_mode()

@router.get("/sales/category")
def sales_by_category(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_sales_by_category()

@router.get("/profit/daily")
def daily_profit(days: int = 7, user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_daily_profit_trend(days)

@router.get("/profit/product")
def profit_by_product(limit: int = 10, user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_profit_by_product(limit)

@router.get("/profit/category")
def profit_by_category(user: UserContext = Depends(require_permission(Permission.ANALYTICS_READ))):
    return get_profit_by_category()
