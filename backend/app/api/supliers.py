from fastapi import APIRouter, Depends
from app.Services.supplier_service import get_suppliers, get_supplier, get_supplier_products, get_supplier_purchase_history
from app.core.auth import require_permission
from app.core.permissions import Permission, UserContext

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])

@router.get("/")
def suppliers(user: UserContext = Depends(require_permission(Permission.SUPPLIERS_READ))):
    return get_suppliers()

@router.get("/{supplier_id}")
def supplier(supplier_id: int, user: UserContext = Depends(require_permission(Permission.SUPPLIERS_READ))):
    return get_supplier(supplier_id)

@router.get("/{supplier_id}/products")
def supplier_products(supplier_id: int, user: UserContext = Depends(require_permission(Permission.SUPPLIERS_READ))):
    return get_supplier_products(supplier_id)

@router.get("/{supplier_id}/purchase-history")
def supplier_purchase_history(supplier_id: int, user: UserContext = Depends(require_permission(Permission.SUPPLIERS_MANAGE))):
    return get_supplier_purchase_history(supplier_id)
