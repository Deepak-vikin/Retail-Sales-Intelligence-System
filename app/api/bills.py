from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.Services.bill_service import (
    create_bill,
    get_bill,
    get_recent_bills,
)


router = APIRouter(prefix="/bills", tags=["Bills"])


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
def add_bill(bill: BillCreate):
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
def recent_bills(limit: int = 100):
    return get_recent_bills(limit)


@router.get("/{bill_id}")
def bill(bill_id: int):
    return get_bill(bill_id)