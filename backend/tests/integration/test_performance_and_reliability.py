import time
import uuid
import jwt
from unittest.mock import MagicMock
from cryptography.hazmat.primitives.asymmetric import ec
from jwt import PyJWKClientError
import pytest
from decimal import Decimal
from datetime import datetime
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import SUPABASE_URL
from app.core.database import connection
from app.core.auth import set_jwks_client, set_employee_lookup_override
from app.core.permissions import AppRole
from app.Services.bill_service import (
    create_bill,
    get_bill,
    get_recent_bills,
    search_bills,
)

client = TestClient(app)

TEST_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key()
TEST_KID = "test-perf-kid-2026"
TEST_EMPLOYEES = {}


class MockJWKSClient:
    def __init__(self):
        self.keys = {TEST_KID: TEST_PUBLIC_KEY}

    def get_signing_key_from_jwt(self, token: str):
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if kid not in self.keys:
            raise PyJWKClientError(f"Signing key with kid '{kid}' not found.")
        mock_key = MagicMock()
        mock_key.key = self.keys[kid]
        return mock_key


@pytest.fixture(autouse=True)
def setup_auth_environment():
    global TEST_EMPLOYEES
    TEST_EMPLOYEES = {}
    mock_jwks = MockJWKSClient()
    set_jwks_client(mock_jwks)
    set_employee_lookup_override(lambda uid: TEST_EMPLOYEES.get(uid))
    yield
    set_jwks_client(None)
    set_employee_lookup_override(None)


def make_token(user_id: str, email: str, role: str) -> str:
    now = int(time.time())
    expected_iss = f"{SUPABASE_URL.rstrip('/')}/auth/v1"
    payload = {
        "sub": user_id,
        "email": email,
        "iss": expected_iss,
        "aud": "authenticated",
        "role": "authenticated",
        "exp": now + 3600,
        "iat": now - 10,
        "user_metadata": {
            "full_name": f"Test {role.title()}",
            "role": role,
            "is_active": True,
        },
    }
    TEST_EMPLOYEES[user_id] = {
        "id": user_id,
        "full_name": f"Test {role.title()}",
        "email": email,
        "role": role,
        "is_active": True,
    }
    return jwt.encode(
        payload,
        TEST_PRIVATE_KEY,
        algorithm="ES256",
        headers={"kid": TEST_KID},
    )


def _get_headers_for_role(role: AppRole) -> dict:
    uid = str(uuid.uuid4())
    token = make_token(uid, f"perf-{role.value}@retail.com", role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def sample_product_and_stock():
    conn = connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.product_id, p.product_name, inv.current_stock
        FROM products p
        JOIN inventory inv ON p.product_id = inv.product_id
        WHERE inv.current_stock > 20
        LIMIT 1;
        """
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None, "At least one product with stock > 20 must exist for performance tests"
    return {"product_id": row[0], "product_name": row[1], "initial_stock": row[2]}


def test_server_timing_header_present():
    """Verify that the FastAPI performance middleware attaches the Server-Timing header."""
    headers = _get_headers_for_role(AppRole.CASHIER)
    res = client.get("/bills/recent?limit=5", headers=headers)
    assert res.status_code == 200
    assert "Server-Timing" in res.headers, "Response must include Server-Timing header"
    assert "total;dur=" in res.headers["Server-Timing"]


def test_create_bill_performance_and_transactional_integrity(sample_product_and_stock):
    """
    Verify create_bill:
    1. Executes without blocking on synchronous neural embeddings.
    2. Atomically decrements inventory.
    3. Prevents duplicate bill creation.
    """
    pid = sample_product_and_stock["product_id"]
    test_bill_id = int(time.time() * 100) % 100000000 + 77000000

    conn = connection()
    cur = conn.cursor()
    cur.execute("SELECT current_stock FROM inventory WHERE product_id = %s;", (pid,))
    stock_before = cur.fetchone()[0]
    conn.close()

    headers = _get_headers_for_role(AppRole.CASHIER)
    payload = {
        "bill_id": test_bill_id,
        "cashier_id": 101,
        "transaction_datetime": datetime.now().isoformat(),
        "payment_mode": "UPI",
        "items": [
            {
                "product_id": pid,
                "quantity": 2,
                "unit_price": 25.0,
                "discount": 0.0,
            }
        ],
    }

    t0 = time.perf_counter()
    res = client.post("/bills/", json=payload, headers=headers)
    dur_ms = (time.perf_counter() - t0) * 1000

    try:
        assert res.status_code == 200, f"Failed: {res.text}"
        data = res.json()
        assert data["bill_id"] == test_bill_id
        assert Decimal(str(data["total_amount"])) == Decimal("50.0")

        # Checkout must complete in reasonable time (well under previous 38s)
        assert dur_ms < 10000, f"Checkout took {dur_ms:.2f}ms, expected < 10000ms (baseline was 38933ms)"

        # Verify inventory was decremented by exactly 2
        conn = connection()
        cur = conn.cursor()
        cur.execute("SELECT current_stock FROM inventory WHERE product_id = %s;", (pid,))
        stock_after = cur.fetchone()[0]
        conn.close()
        assert stock_after == stock_before - 2, f"Expected stock {stock_before - 2}, got {stock_after}"

        # Verify duplicate bill submission is blocked
        res_dup = client.post("/bills/", json=payload, headers=headers)
        assert res_dup.status_code == 400
        assert f"Bill {test_bill_id} already exists" in res_dup.json()["detail"]

    finally:
        # Cleanup test bill
        conn = connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM bill_items WHERE bill_id = %s;", (test_bill_id,))
        cur.execute("DELETE FROM bills WHERE bill_id = %s;", (test_bill_id,))
        cur.execute("UPDATE inventory SET current_stock = %s WHERE product_id = %s;", (stock_before, pid))
        conn.commit()
        conn.close()


def test_get_bill_optimized_retrieval(sample_product_and_stock):
    """Verify single-roundtrip get_bill returns accurate bill and item structure."""
    recent = get_recent_bills(limit=1)
    assert len(recent) > 0, "At least one bill should exist"
    bill_id = recent[0][0]

    t0 = time.perf_counter()
    data = get_bill(bill_id)
    dur = (time.perf_counter() - t0) * 1000

    assert data is not None
    assert "bill" in data
    assert "items" in data
    assert data["bill"][0] == bill_id
    assert isinstance(data["items"], list)
    assert dur < 8000, f"get_bill took {dur:.2f}ms, expected < 8000ms"


def test_rbac_security_preservation_on_billing():
    """Verify Owner/Cashier allowed, Programmer forbidden on billing endpoints."""
    # Cashier allowed on /bills/recent
    res_cashier = client.get("/bills/recent?limit=5", headers=_get_headers_for_role(AppRole.CASHIER))
    assert res_cashier.status_code == 200

    # Programmer forbidden on /bills/recent
    res_prog = client.get("/bills/recent?limit=5", headers=_get_headers_for_role(AppRole.PROGRAMMER))
    assert res_prog.status_code == 403

    # Unauthenticated rejected
    res_anon = client.get("/bills/recent?limit=5")
    assert res_anon.status_code == 401
