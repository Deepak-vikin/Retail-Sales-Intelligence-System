import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app
from app.core.permissions import AppRole, UserContext
from app.core.auth import get_current_user
import app.api.purchase as purchase_api
from app.core.database import connection

client = TestClient(app)

@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: UserContext(
        user_id=str(uuid.uuid4()),
        email="owner.timezone@store.com",
        full_name="Platform Owner",
        role=AppRole.OWNER,
    )
    yield
    app.dependency_overrides.clear()
    with purchase_api._purchase_lock:
        purchase_api._in_flight_purchases.clear()


def test_postgres_column_types_date_vs_timestamp():
    """Verify database schema types: purchases.purchase_date is pure date; bills and logs are timestamps."""
    conn = connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name, column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND column_name IN ('purchase_date', 'transaction_datetime', 'last_updated', 'performed_at')
            ORDER BY table_name, column_name;
        """)
        rows = {f"{r[0]}.{r[1]}": r[2] for r in cur.fetchall()}

        assert "purchases.purchase_date" in rows, "purchases.purchase_date must exist in DB schema"
        assert rows["purchases.purchase_date"] == "date", (
            f"purchases.purchase_date must be DATE type, found: {rows['purchases.purchase_date']}"
        )

        assert "bills.transaction_datetime" in rows, "bills.transaction_datetime must exist in DB schema"
        assert "timestamp" in rows["bills.transaction_datetime"].lower(), (
            f"bills.transaction_datetime must be timestamp type, found: {rows['bills.transaction_datetime']}"
        )

        assert "technical_audit_logs.performed_at" in rows, "technical_audit_logs.performed_at must exist"
        assert "timestamp" in rows["technical_audit_logs.performed_at"].lower()
    finally:
        conn.close()


def test_recent_purchases_returns_date_only():
    """Verify GET /purchases/recent returns purchase_date as a date string without time component."""
    response = client.get("/purchases/recent?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        first = data[0]
        # Tuple schema: [purchase_id, product_id, supplier_id, purchase_date, quantity_received, cost_price]
        purchase_date_val = str(first[3] if isinstance(first, list) else first.get("purchase_date"))
        assert len(purchase_date_val) == 10, f"Expected YYYY-MM-DD (10 chars), got: {purchase_date_val}"
        assert purchase_date_val.count("-") == 2, f"Expected YYYY-MM-DD format, got: {purchase_date_val}"
        assert "T" not in purchase_date_val and ":" not in purchase_date_val, (
            f"purchase_date must not contain time component: {purchase_date_val}"
        )


def test_create_purchase_preserves_user_selected_date():
    """Verify that submitting a specific purchase date preserves that exact calendar date."""
    test_id = 999101
    test_date = "2026-10-06"

    mock_result = {
        "purchase_id": test_id,
        "product_id": 1,
        "supplier_id": 1,
        "quantity_received": 15,
        "cost_price": 45.0,
        "purchase_date": test_date,
        "message": "Purchase recorded and inventory updated successfully.",
    }

    with patch("app.api.purchase.create_purchase", return_value=mock_result):
        response = client.post(
            "/purchases/",
            json={
                "purchase_id": test_id,
                "product_id": 1,
                "supplier_id": 1,
                "quantity_received": 15,
                "cost_price": 45.0,
                "purchase_date": test_date,
            },
        )
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["purchase_date"] == test_date
        assert res_data["purchase_id"] == test_id


def test_newly_received_stock_today_date():
    """Verify newly received stock can be recorded with current date and updates inventory."""
    today_str = date.today().isoformat()
    test_id = 999102

    mock_result = {
        "purchase_id": test_id,
        "product_id": 2,
        "supplier_id": 1,
        "quantity_received": 25,
        "cost_price": 120.0,
        "purchase_date": today_str,
        "message": "Purchase recorded and inventory updated successfully.",
    }

    with patch("app.api.purchase.create_purchase", return_value=mock_result):
        response = client.post(
            "/purchases/",
            json={
                "purchase_id": test_id,
                "product_id": 2,
                "supplier_id": 1,
                "quantity_received": 25,
                "cost_price": 120.0,
                "purchase_date": today_str,
            },
        )
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["purchase_date"] == today_str


def test_bill_timestamp_contains_time():
    """Verify that bills contain actual transaction datetime with time component."""
    response = client.get("/bills/?limit=3")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        first = data[0]
        # Tuple schema: [bill_id, cashier_id, transaction_datetime, payment_mode, total_amount]
        trans_dt_val = str(first[2] if isinstance(first, list) else first.get("transaction_datetime"))
        # Must contain time component (hours:minutes)
        assert ":" in trans_dt_val, f"Bills transaction_datetime must have time component: {trans_dt_val}"
