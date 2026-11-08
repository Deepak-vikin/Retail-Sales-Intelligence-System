from fastapi import APIRouter
from app.Services.inventory_service import get_inventory, get_low_stock_products, get_out_of_stock_products, get_stock_value

router = APIRouter(prefix="/inventory", tags=["Inventory"])

@router.get("/")
def inventory():
    return get_inventory()

@router.get("/low-stock")
def low_stock_products():
    return get_low_stock_products()

@router.get("/out-of-stock")
def out_of_stock_products():
    return get_out_of_stock_products()

@router.get("/stock-value")
def stock_value():
    return get_stock_value()




