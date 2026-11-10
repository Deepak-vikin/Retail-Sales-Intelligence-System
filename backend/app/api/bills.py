import os
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel, Field
from app.Services.bill_service import (
    create_bill,
    get_bill,
    get_recent_bills,
    search_bills,
)
from app.Services.pdf_service import generate_receipt_pdf
from app.core.auth import require_permission
from app.core.permissions import Permission, UserContext

router = APIRouter(prefix="/bills", tags=["Bills"])

def _get_configured_store_info() -> dict:
    info = {
        "name": os.getenv("STORE_NAME") or "Retail Sales Intelligence Platform",
    }
    if os.getenv("STORE_ADDRESS"):
        info["address"] = os.getenv("STORE_ADDRESS")
    if os.getenv("STORE_GSTIN"):
        info["gstin"] = os.getenv("STORE_GSTIN")
    if os.getenv("STORE_PHONE"):
        info["phone"] = os.getenv("STORE_PHONE")
    return info

class BillItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(gt=0)
    discount: Decimal = Field(default=Decimal("0"), ge=0)

class BillCreate(BaseModel):
    bill_id: int
    cashier_id: int
    transaction_datetime: datetime
    payment_mode: str
    items: list[BillItemCreate] = Field(min_length=1)

@router.post("/")
def add_bill(bill: BillCreate, user: UserContext = Depends(require_permission(Permission.BILLING_CREATE))):
    try:
        return create_bill(
            bill_id=bill.bill_id,
            cashier_id=bill.cashier_id,
            transaction_datetime=bill.transaction_datetime,
            payment_mode=bill.payment_mode,
            items=[
                item.model_dump()
                for item in bill.items
            ],
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

@router.get("/")
def recent_bills(limit: int = 50, user: UserContext = Depends(require_permission(Permission.BILLING_MANAGE))):
    return get_recent_bills(limit)

@router.get("/recent")
def recent_bills_read_only(
    limit: int = 50,
    user: UserContext = Depends(require_permission(Permission.BILLING_READ)),
):
    # Enforce hard maximum of 50 records to prevent unrestricted historical listing
    effective_limit = min(max(1, limit), 50)
    return get_recent_bills(effective_limit)

@router.get("/search")
def search_bills_endpoint(
    query: str,
    limit: int = 50,
    user: UserContext = Depends(require_permission(Permission.BILLING_READ)),
):
    if not query or not query.strip():
        return []
    return search_bills(query.strip(), limit=limit)

@router.get("/{bill_id}/pdf")
def download_receipt_pdf(
    bill_id: int,
    user: UserContext = Depends(require_permission(Permission.BILLING_READ)),
):
    bill_data = get_bill(bill_id)
    if not bill_data:
        raise HTTPException(status_code=404, detail=f"Bill #{bill_id} not found.")

    store_info = _get_configured_store_info()
    pdf_bytes = generate_receipt_pdf(bill_data, store_info=store_info)
    filename = f"receipt_BILL-{bill_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )

@router.get("/{bill_id}")
def bill(bill_id: int, user: UserContext = Depends(require_permission(Permission.BILLING_READ))):
    bill_data = get_bill(bill_id)
    if not bill_data:
        raise HTTPException(status_code=404, detail=f"Bill #{bill_id} not found.")
    bill_data["store"] = _get_configured_store_info()
    return bill_data
