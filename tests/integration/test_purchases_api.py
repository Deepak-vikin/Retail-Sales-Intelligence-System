from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_create_purchase_updates_inventory():
    purchase_id = 900001
    product_id = 34
    supplier_id = 5
    quantity = 10
    cost_price = 420
    purchase_date = "2026-10-06"

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