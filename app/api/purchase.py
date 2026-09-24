from fastapi import APIRouter
from app.Services.purchase_service import * 

router=APIRouter(prefix="/purchase", tags=["Purchase"])
@router.get("/")
def purchases():
    return get_purchase()
@router.get("/{purchase_id}")
def purchase(purchase_id):
    return get_purchase(purchase_id)
@router.get("/product/{product_id}")
def product_purchase(product_id):
    return get_product_purchase(product_id)
@router.get("/supplier/{supplier_id}")
def supplier_purchase(supplier_id):
    return get_supplier_purchase(supplier_id)
@router.get("/date-range/{start_date}/{end_date}")
def date_range_purchase(start_date,end_date):
    return get_date_range_purchase(start_date,end_date)  
@router.get("/add")
def add_purchase():
    return add_purchase()