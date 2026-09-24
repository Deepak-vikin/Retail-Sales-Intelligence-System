from fastapi import APIRouter
from app.Services.product_service import get_products

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("/")
def products():
    return get_products()