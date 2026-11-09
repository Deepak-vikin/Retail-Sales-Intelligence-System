from datetime import date
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from app.Services.purchase_service import (
    create_purchase,
    get_all_purchases,
    get_purchase,
    get_product_purchases,
    get_recent_purchases,
    get_total_purchase_cost,
    get_total_purchased_quantity,
)
from app.core.auth import require_permission
from app.core.permissions import Permission, UserContext

router = APIRouter(prefix="/purchases", tags=["Purchases"])

class PurchaseCreate(BaseModel):
    purchase_id: int
    product_id: int
    supplier_id: int
    quantity_received: int = Field(gt=0)
    cost_price: Decimal = Field(gt=0)
    purchase_date: date

@router.post("/")
def add_purchase(purchase: PurchaseCreate, user: UserContext = Depends(require_permission(Permission.PURCHASES_MANAGE))):
    try:
        return create_purchase(
            purchase_id=purchase.purchase_id,
            product_id=purchase.product_id,
            supplier_id=purchase.supplier_id,
            quantity_received=purchase.quantity_received,
            cost_price=purchase.cost_price,
            purchase_date=purchase.purchase_date,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to record purchase."
        )

@router.get("/")
def purchases(user: UserContext = Depends(require_permission(Permission.PURCHASES_READ))):
    return get_all_purchases()

@router.get("/recent")
def recent_purchases(limit: int = 10, user: UserContext = Depends(require_permission(Permission.PURCHASES_READ))):
    return get_recent_purchases(limit)

@router.get("/total-cost")
def total_cost(user: UserContext = Depends(require_permission(Permission.PURCHASES_MANAGE))):
    return get_total_purchase_cost()

@router.get("/total-quantity")
def total_quantity(user: UserContext = Depends(require_permission(Permission.PURCHASES_READ))):
    return get_total_purchased_quantity()

@router.get("/product/{product_id}")
def product_purchases(product_id: int, user: UserContext = Depends(require_permission(Permission.PURCHASES_READ))):
    return get_product_purchases(product_id)

@router.get("/{purchase_id}")
def purchase(purchase_id: int, user: UserContext = Depends(require_permission(Permission.PURCHASES_READ))):
    return get_purchase(purchase_id)
