from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_create_bill_updates_inventory():
    bill_id = 900001
    product_id = 34
    quantity = 2
    unit_price = 450
    discount = 0

    response = client.post(
        "/bills/",
        json={
            "bill_id": bill_id,
            "cashier_id": 101,
            "transaction_datetime": "2026-10-06T18:30:00",
            "payment_mode": "UPI",
            "items": [
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "discount": discount,
                }
            ],
        },
    )

    print("STATUS:", response.status_code)
    print("RESPONSE:", response.json())

    assert response.status_code == 200

    data = response.json()

    assert data["bill_id"] == bill_id
    assert data["cashier_id"] == 101
    assert data["payment_mode"] == "UPI"
    assert data["total_amount"] == 900
    assert data["message"] == "Bill created and inventory updated successfully."