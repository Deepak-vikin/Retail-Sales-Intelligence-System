from fastapi import APIRouter, Depends
from app.Services.product_service import get_products
from app.core.auth import require_permission
from app.core.permissions import Permission, UserContext

router = APIRouter(prefix="/products", tags=["Products"])

@router.get("/")
def products(user: UserContext = Depends(require_permission(Permission.PRODUCTS_READ))):
    return get_products()
