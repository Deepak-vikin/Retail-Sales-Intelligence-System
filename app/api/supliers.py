from fastapi import APIRouter
from app.Services.supplier_service import get_suppliers, get_supplier, get_supplier_products, get_supplier_purchase_history
router = APIRouter(prefix="/suppliers", tags=["Suppliers"])
@router.get("/")
def suppliers():
    return get_suppliers()
@router.get("/{supplier_id}")
def supplier(supplier_id):
    return get_supplier(supplier_id)
@router.get("/{supplier_id}/products")
def supplier_products(supplier_id):
    return get_supplier_products(supplier_id)
@router.get("/{supplier_id}/purchase-history")
def supplier_purchase_history(supplier_id):
    return get_supplier_purchase_history(supplier_id)