from datetime import date
from decimal import Decimal
import threading
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

_purchase_lock = threading.Lock()
_in_flight_purchases = set()

class PurchaseCreate(BaseModel):
    purchase_id: int
    product_id: int
    supplier_id: int
    quantity_received: int = Field(gt=0)
    cost_price: Decimal = Field(gt=0)
    purchase_date: date

@router.post("/")
def add_purchase(purchase: PurchaseCreate, user: UserContext = Depends(require_permission(Permission.PURCHASES_MANAGE))):
    with _purchase_lock:
        if purchase.purchase_id in _in_flight_purchases:
            raise HTTPException(
                status_code=409,
                detail=f"Purchase reference #{purchase.purchase_id} is currently being processed. Duplicate submission prevented."
            )
        _in_flight_purchases.add(purchase.purchase_id)

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
        err_msg = str(error)
        if "already exists" in err_msg.lower():
            raise HTTPException(
                status_code=409,
                detail=f"Purchase reference #{purchase.purchase_id} already exists."
            )
        raise HTTPException(status_code=400, detail=err_msg)
    except Exception as e:
        err_msg = str(e).lower()
        if "duplicate key" in err_msg or "unique constraint" in err_msg or "already exists" in err_msg:
            raise HTTPException(
                status_code=409,
                detail=f"Purchase reference #{purchase.purchase_id} already exists."
            )
        raise HTTPException(
            status_code=500,
            detail="Failed to record purchase."
        )
    finally:
        with _purchase_lock:
            _in_flight_purchases.discard(purchase.purchase_id)

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
