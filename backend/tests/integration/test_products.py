"""
Integration tests – bill service.

Verifies that get_recent_bills() and get_bill() return valid data.
All service calls happen inside test functions (not at import time).
"""
from app.Services.bill_service import get_bill, get_recent_bills


def test_get_recent_bills_returns_list():
    """get_recent_bills(5) should return a non-empty list of tuples."""
    bills = get_recent_bills(5)
    assert isinstance(bills, list), "Expected a list"
    assert len(bills) > 0, "Expected at least one bill"


def test_get_bill_returns_dict():
    """get_bill(bill_id) should return a dict with 'bill' and 'items' keys."""
    bills = get_recent_bills(1)
    assert bills, "No bills found – cannot test get_bill()"
    bill_id = bills[0][0]
    result = get_bill(bill_id)
    assert isinstance(result, dict), "Expected a dict"
    assert "bill" in result, "'bill' key missing from result"
    assert "items" in result, "'items' key missing from result"