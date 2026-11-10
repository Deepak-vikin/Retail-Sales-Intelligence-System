import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app
from app.core.permissions import AppRole, UserContext
from app.core.auth import get_current_user
import app.api.purchase as purchase_api

client = TestClient(app)

@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: UserContext(
        user_id=str(uuid.uuid4()),
        email="manager.stock@store.com",
        full_name="Inventory Manager",
        role=AppRole.MANAGER,
    )
    yield
    app.dependency_overrides.clear()
    with purchase_api._purchase_lock:
        purchase_api._in_flight_purchases.clear()

def test_create_purchase_updates_inventory():
    purchase_id = 900001
    product_id = 34
    supplier_id = 5
    quantity = 10
    cost_price = 420.0
    purchase_date = "2026-10-06"

    mock_result = {
        "purchase_id": purchase_id,
        "product_id": product_id,
        "supplier_id": supplier_id,
        "quantity_received": quantity,
        "cost_price": cost_price,
        "purchase_date": purchase_date,
        "message": "Purchase recorded and inventory updated successfully.",
    }

    with patch("app.api.purchase.create_purchase", return_value=mock_result):
        response = client.post(
            "/purchases/",
            json={
                "purchase_id": purchase_id,
                "product_id": product_id,
                "supplier_id": supplier_id,
                "quantity_received": quantity,
                "cost_price": cost_price,
                "purchase_date": purchase_date,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["purchase_id"] == purchase_id
        assert data["product_id"] == product_id
        assert data["quantity_received"] == quantity

def test_duplicate_purchase_id_rejected_with_409():
    purchase_id = 900002
    with patch("app.api.purchase.create_purchase", side_effect=ValueError(f"Purchase {purchase_id} already exists.")):
        response = client.post(
            "/purchases/",
            json={
                "purchase_id": purchase_id,
                "product_id": 1,
                "supplier_id": 1,
                "quantity_received": 10,
                "cost_price": 50.0,
                "purchase_date": "2026-11-10",
            },
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

def test_in_flight_duplicate_purchase_rejected_with_409():
    purchase_id = 900003
    # Simulate an active in-flight request
    with purchase_api._purchase_lock:
        purchase_api._in_flight_purchases.add(purchase_id)

    response = client.post(
        "/purchases/",
        json={
            "purchase_id": purchase_id,
            "product_id": 1,
            "supplier_id": 1,
            "quantity_received": 10,
            "cost_price": 50.0,
            "purchase_date": "2026-11-10",
        },
    )
    assert response.status_code == 409
    assert "currently being processed" in response.json()["detail"].lower()

def test_cashier_denied_purchase_creation():
    app.dependency_overrides[get_current_user] = lambda: UserContext(
        user_id=str(uuid.uuid4()),
        email="cashier.user@store.com",
        full_name="Cashier User",
        role=AppRole.CASHIER,
    )

    response = client.post(
        "/purchases/",
        json={
            "purchase_id": 900004,
            "product_id": 1,
            "supplier_id": 1,
            "quantity_received": 5,
            "cost_price": 100.0,
            "purchase_date": "2026-11-10",
        },
    )
    assert response.status_code == 403
