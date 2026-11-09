from fastapi import APIRouter, Depends
from app.Services.inventory_service import get_inventory, get_low_stock_products, get_out_of_stock_products, get_stock_value
from app.core.auth import require_permission
from app.core.permissions import Permission, UserContext

router = APIRouter(prefix="/inventory", tags=["Inventory"])

@router.get("/")
def inventory(user: UserContext = Depends(require_permission(Permission.INVENTORY_READ))):
    return get_inventory()

@router.get("/low-stock")
def low_stock_products(user: UserContext = Depends(require_permission(Permission.INVENTORY_READ))):
    return get_low_stock_products()

@router.get("/out-of-stock")
def out_of_stock_products(user: UserContext = Depends(require_permission(Permission.INVENTORY_READ))):
    return get_out_of_stock_products()

@router.get("/stock-value")
def stock_value(user: UserContext = Depends(require_permission(Permission.INVENTORY_MANAGE))):
    return get_stock_value()
