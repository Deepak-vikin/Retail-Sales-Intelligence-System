from fastapi import APIRouter
from app.Services.bill_service import get_bill, get_recent_bills

router=APIRouter()
@router.get("/")
def recent_bills():
    return get_recent_bills()
@router.get("/{bill_id}")
def bill(bill_id):
    return get_bill(bill_id)
    
