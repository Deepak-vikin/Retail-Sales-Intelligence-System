import os
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock
import jwt
from jwt import PyJWKClientError
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import SUPABASE_URL
from app.core.database import connection
from app.core.auth import set_jwks_client, set_employee_lookup_override

client = TestClient(app)

TEST_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key()
TEST_KID = "test-bills-kid-2026"

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


@pytest.fixture(scope="module")
def setup_test_bills():
    """
    Ensure we have test bills in the database, including some older ones.
    """
    conn = connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT product_id FROM inventory WHERE current_stock > 10 LIMIT 2;")
        prods = cursor.fetchall()
        if not prods:
            pytest.skip("No products with stock found in DB for bill testing")

        prod_id_1 = prods[0][0]
        prod_id_2 = prods[1][0] if len(prods) > 1 else prod_id_1

        cursor.execute("SELECT COALESCE(MAX(item_id), 0) FROM bill_items;")
        max_item_id = cursor.fetchone()[0]

        created_bill_ids = []
        base_id = 999000
        for i in range(3):
            test_b_id = base_id + i
            cursor.execute("DELETE FROM bill_items WHERE bill_id = %s;", (test_b_id,))
            cursor.execute("DELETE FROM bills WHERE bill_id = %s;", (test_b_id,))

            dt = datetime(2026, 1, 15 + i, 10, 30, 0)
            cursor.execute(
                """
                INSERT INTO bills (bill_id, cashier_id, transaction_datetime, payment_mode, total_amount)
                VALUES (%s, 101, %s, 'card', 150.00);
                """,
                (test_b_id, dt),
            )
            max_item_id += 1
            item1_id = max_item_id
            max_item_id += 1
            item2_id = max_item_id
            cursor.execute(
                """
                INSERT INTO bill_items (item_id, bill_id, product_id, quantity, unit_price, discount, line_total)
                VALUES (%s, %s, %s, 2, 50.00, 0.00, 100.00),
                       (%s, %s, %s, 1, 50.00, 0.00, 50.00);
                """,
                (item1_id, test_b_id, prod_id_1, item2_id, test_b_id, prod_id_2),
            )
            created_bill_ids.append(test_b_id)

        conn.commit()
        yield {
            "bill_ids": created_bill_ids,
            "prod_ids": [prod_id_1, prod_id_2],
        }
    finally:
        conn.close()


def test_recent_bills_endpoint_permissions_and_capping(setup_test_bills):
    """
    Tests for GET /bills/recent:
    - Owner can retrieve Recent Bills (200).
    - Manager can retrieve Recent Bills (200).
    - Cashier can retrieve Recent Bills (200).
    - Programmer receives HTTP 403.
    - Capped at hard maximum of 50 bills even if ?limit=500 requested.
    - Ordered newest first (b.transaction_datetime DESC, b.bill_id DESC).
    """
    owner_token = make_token(str(uuid.uuid4()), "owner@store.com", "owner")
    mgr_token = make_token(str(uuid.uuid4()), "mgr@store.com", "manager")
    cashier_token = make_token(str(uuid.uuid4()), "cashier@store.com", "cashier")
    prog_token = make_token(str(uuid.uuid4()), "prog@store.com", "programmer")

    # Owner: 200
    res_owner = client.get("/bills/recent?limit=50", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_owner.status_code == 200
    assert len(res_owner.json()) <= 50

    # Manager: 200
    res_mgr = client.get("/bills/recent?limit=50", headers={"Authorization": f"Bearer {mgr_token}"})
    assert res_mgr.status_code == 200
    assert len(res_mgr.json()) <= 50

    # Cashier: 200
    res_cashier = client.get("/bills/recent?limit=50", headers={"Authorization": f"Bearer {cashier_token}"})
    assert res_cashier.status_code == 200
    bills = res_cashier.json()
    assert isinstance(bills, list)
    assert len(bills) <= 50

    # Check descending order:
    if len(bills) > 1:
        for i in range(len(bills) - 1):
            dt_curr = bills[i][2]
            dt_next = bills[i + 1][2]
            assert dt_curr >= dt_next
            if dt_curr == dt_next:
                assert bills[i][0] >= bills[i + 1][0]

    # Enforce hard maximum of 50 even when requested limit=500
    res_overflow = client.get("/bills/recent?limit=500", headers={"Authorization": f"Bearer {cashier_token}"})
    assert res_overflow.status_code == 200
    assert len(res_overflow.json()) <= 50

    # Programmer: 403
    res_prog = client.get("/bills/recent?limit=50", headers={"Authorization": f"Bearer {prog_token}"})
    assert res_prog.status_code == 403


def test_cashier_denied_access_to_unrestricted_bills_ledger():
    """
    Verify that Cashier remains strictly forbidden from unrestricted GET /bills/ (HTTP 403).
    Only Owner and Manager retain access.
    """
    cashier_token = make_token(str(uuid.uuid4()), "cashier@store.com", "cashier")
    owner_token = make_token(str(uuid.uuid4()), "owner@store.com", "owner")
    mgr_token = make_token(str(uuid.uuid4()), "mgr@store.com", "manager")

    assert client.get("/bills/", headers={"Authorization": f"Bearer {cashier_token}"}).status_code == 403
    assert client.get("/bills/", headers={"Authorization": f"Bearer {owner_token}"}).status_code == 200
    assert client.get("/bills/", headers={"Authorization": f"Bearer {mgr_token}"}).status_code == 200


def test_bill_id_search_exact_and_partial(setup_test_bills):
    """
    Test exact and partial Bill ID search.
    Stripping of 'BILL-', '#' prefixes is supported.
    """
    test_id = setup_test_bills["bill_ids"][0]
    manager_token = make_token(str(uuid.uuid4()), "manager@store.com", "manager")

    # Exact search
    res = client.get(f"/bills/search?query={test_id}", headers={"Authorization": f"Bearer {manager_token}"})
    assert res.status_code == 200
    results = res.json()
    assert any(b[0] == test_id for b in results)

    # Prefix with 'BILL-'
    res_prefix = client.get(f"/bills/search?query=BILL-{test_id}", headers={"Authorization": f"Bearer {manager_token}"})
    assert res_prefix.status_code == 200
    results_prefix = res_prefix.json()
    assert any(b[0] == test_id for b in results_prefix)

    # Prefix with '#'
    res_hash = client.get("/bills/search", params={"query": f"#{test_id}"}, headers={"Authorization": f"Bearer {manager_token}"})
    assert res_hash.status_code == 200
    results_hash = res_hash.json()
    assert any(b[0] == test_id for b in results_hash)

    # Partial search (first 4 digits '9990')
    partial_q = str(test_id)[:4]
    res_partial = client.get(f"/bills/search?query={partial_q}", headers={"Authorization": f"Bearer {manager_token}"})
    assert res_partial.status_code == 200
    results_partial = res_partial.json()
    assert any(b[0] == test_id for b in results_partial)


def test_search_finds_bills_older_than_latest_50(setup_test_bills):
    """
    Verify search queries the entire historical bill dataset, finding bills
    older than the automatically loaded latest 50 records.
    """
    old_test_id = setup_test_bills["bill_ids"][0]
    cashier_token = make_token(str(uuid.uuid4()), "cashier@store.com", "cashier")

    # Fetch top 50 recent bills via /recent
    res_recent = client.get("/bills/recent?limit=50", headers={"Authorization": f"Bearer {cashier_token}"})
    assert res_recent.status_code == 200
    recent_ids = [b[0] for b in res_recent.json()]
    assert old_test_id not in recent_ids, "Test bill should be older than latest 50 bills"

    # Search specifically retrieves it from the full historical database
    res_search = client.get(f"/bills/search?query={old_test_id}", headers={"Authorization": f"Bearer {cashier_token}"})
    assert res_search.status_code == 200
    search_ids = [b[0] for b in res_search.json()]
    assert old_test_id in search_ids


def test_bill_id_search_no_match():
    """
    Searching for non-existent bill ID returns empty list [].
    """
    cashier_token = make_token(str(uuid.uuid4()), "cashier@store.com", "cashier")
    res = client.get("/bills/search?query=999999999999", headers={"Authorization": f"Bearer {cashier_token}"})
    assert res.status_code == 200
    assert res.json() == []


def test_bill_id_search_empty_query():
    """
    Empty or whitespace query returns empty list.
    """
    cashier_token = make_token(str(uuid.uuid4()), "cashier@store.com", "cashier")
    res = client.get("/bills/search?query=   ", headers={"Authorization": f"Bearer {cashier_token}"})
    assert res.status_code == 200
    assert res.json() == []


def test_receipt_view_details_no_fabricated_store_info(setup_test_bills):
    """
    GET /bills/{bill_id} returns full bill metadata and verified store metadata.
    Does NOT contain fabricated details like 'Store #101', 'Commercial Boulevard', or '29ABCDE1234F1Z5'.
    """
    test_id = setup_test_bills["bill_ids"][0]
    cashier_token = make_token(str(uuid.uuid4()), "cashier@store.com", "cashier")

    res = client.get(f"/bills/{test_id}", headers={"Authorization": f"Bearer {cashier_token}"})
    assert res.status_code == 200
    data = res.json()
    assert "bill" in data
    assert "items" in data
    assert data["bill"][0] == test_id
    assert len(data["items"]) == 2

    # Check store info
    store = data.get("store", {})
    assert "Store #101" not in store.get("name", "")
    assert "Commercial Boulevard" not in str(store)
    assert "29ABCDE1234F1Z5" not in str(store)
    # If address or gstin not configured, they should be absent
    if not os.getenv("STORE_ADDRESS"):
        assert "address" not in store
    if not os.getenv("STORE_GSTIN"):
        assert "gstin" not in store


def test_receipt_pdf_download_no_fabricated_store_details(setup_test_bills):
    """
    GET /bills/{bill_id}/pdf returns valid PDF without fabricated store metadata.
    """
    test_id = setup_test_bills["bill_ids"][0]
    owner_token = make_token(str(uuid.uuid4()), "owner@store.com", "owner")

    res = client.get(f"/bills/{test_id}/pdf", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert f'filename="receipt_BILL-{test_id}.pdf"' in res.headers["content-disposition"]
    assert res.content.startswith(b"%PDF-1.4")
    assert b"%%EOF" in res.content

    # Ensure no fabricated placeholder strings exist in PDF bytes
    content_str = res.content.decode("latin-1")
    assert "Store #101" not in content_str
    assert "Commercial Boulevard" not in content_str
    assert "29ABCDE1234F1Z5" not in content_str
    assert "+91 98765 43210" not in content_str


def test_receipt_pdf_with_configured_store_details(setup_test_bills, monkeypatch):
    """
    When store details are explicitly configured via environment variables,
    they are rendered cleanly in the PDF.
    """
    monkeypatch.setenv("STORE_NAME", "Apex Retail Supermart")
    monkeypatch.setenv("STORE_ADDRESS", "Plot 42, Outer Ring Road, Hyderabad")
    monkeypatch.setenv("STORE_GSTIN", "36AABCA1234C1Z9")
    monkeypatch.setenv("STORE_PHONE", "+91 40 1234 5678")

    test_id = setup_test_bills["bill_ids"][0]
    cashier_token = make_token(str(uuid.uuid4()), "cashier@store.com", "cashier")

    res = client.get(f"/bills/{test_id}/pdf", headers={"Authorization": f"Bearer {cashier_token}"})
    assert res.status_code == 200
    content_str = res.content.decode("latin-1")
    assert "Apex Retail Supermart" in content_str
    assert "Plot 42, Outer Ring Road, Hyderabad" in content_str
    assert "36AABCA1234C1Z9" in content_str
    assert "+91 40 1234 5678" in content_str


def test_receipt_pdf_download_not_found():
    """
    GET /bills/{bill_id}/pdf for nonexistent bill returns 404.
    """
    owner_token = make_token(str(uuid.uuid4()), "owner@store.com", "owner")
    res = client.get("/bills/888888888/pdf", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 404


def test_role_permissions_matrix(setup_test_bills):
    """
    Validate RBAC matrix for bill management:
    - Owner: GET /bills/ (200), /bills/recent (200), search (200), view receipt (200), download pdf (200)
    - Manager: GET /bills/ (200), /bills/recent (200), search (200), view receipt (200), download pdf (200)
    - Cashier: GET /bills/ (403), /bills/recent (200), search (200), view receipt (200), download pdf (200)
    - Programmer: all billing endpoints return 403
    """
    test_id = setup_test_bills["bill_ids"][0]
    owner_token = make_token(str(uuid.uuid4()), "owner@store.com", "owner")
    mgr_token = make_token(str(uuid.uuid4()), "mgr@store.com", "manager")
    cashier_token = make_token(str(uuid.uuid4()), "cash@store.com", "cashier")
    prog_token = make_token(str(uuid.uuid4()), "prog@store.com", "programmer")

    # 1. Owner
    assert client.get("/bills/?limit=10", headers={"Authorization": f"Bearer {owner_token}"}).status_code == 200
    assert client.get("/bills/recent?limit=10", headers={"Authorization": f"Bearer {owner_token}"}).status_code == 200
    assert client.get(f"/bills/search?query={test_id}", headers={"Authorization": f"Bearer {owner_token}"}).status_code == 200
    assert client.get(f"/bills/{test_id}", headers={"Authorization": f"Bearer {owner_token}"}).status_code == 200
    assert client.get(f"/bills/{test_id}/pdf", headers={"Authorization": f"Bearer {owner_token}"}).status_code == 200

    # 2. Manager
    assert client.get("/bills/?limit=10", headers={"Authorization": f"Bearer {mgr_token}"}).status_code == 200
    assert client.get("/bills/recent?limit=10", headers={"Authorization": f"Bearer {mgr_token}"}).status_code == 200
    assert client.get(f"/bills/search?query={test_id}", headers={"Authorization": f"Bearer {mgr_token}"}).status_code == 200
    assert client.get(f"/bills/{test_id}", headers={"Authorization": f"Bearer {mgr_token}"}).status_code == 200
    assert client.get(f"/bills/{test_id}/pdf", headers={"Authorization": f"Bearer {mgr_token}"}).status_code == 200

    # 3. Cashier
    # Cashier cannot view the unrestricted store-wide historical ledger
    assert client.get("/bills/?limit=10", headers={"Authorization": f"Bearer {cashier_token}"}).status_code == 403
    # Cashier CAN view recent bills (capped at 50)
    assert client.get("/bills/recent?limit=10", headers={"Authorization": f"Bearer {cashier_token}"}).status_code == 200
    # Cashier CAN search by bill ID
    assert client.get(f"/bills/search?query={test_id}", headers={"Authorization": f"Bearer {cashier_token}"}).status_code == 200
    # Cashier CAN view individual receipt
    assert client.get(f"/bills/{test_id}", headers={"Authorization": f"Bearer {cashier_token}"}).status_code == 200
    # Cashier CAN download receipt PDF
    assert client.get(f"/bills/{test_id}/pdf", headers={"Authorization": f"Bearer {cashier_token}"}).status_code == 200

    # 4. Programmer (Forbidden on all billing endpoints)
    assert client.get("/bills/?limit=10", headers={"Authorization": f"Bearer {prog_token}"}).status_code == 403
    assert client.get("/bills/recent?limit=10", headers={"Authorization": f"Bearer {prog_token}"}).status_code == 403
    assert client.get(f"/bills/search?query={test_id}", headers={"Authorization": f"Bearer {prog_token}"}).status_code == 403
    assert client.get(f"/bills/{test_id}", headers={"Authorization": f"Bearer {prog_token}"}).status_code == 403
    assert client.get(f"/bills/{test_id}/pdf", headers={"Authorization": f"Bearer {prog_token}"}).status_code == 403


def test_pos_checkout_creates_and_serves_pdf(setup_test_bills):
    """
    Verify POS checkout creates a bill, which can then be fetched and downloaded as PDF.
    """
    cashier_token = make_token(str(uuid.uuid4()), "cashier_pos@store.com", "cashier")
    new_bill_id = 999988
    prod_id = setup_test_bills["prod_ids"][0]

    payload = {
        "bill_id": new_bill_id,
        "cashier_id": 105,
        "transaction_datetime": datetime.now(timezone.utc).isoformat(),
        "payment_mode": "cash",
        "items": [
            {
                "product_id": prod_id,
                "quantity": 3,
                "unit_price": 45.00,
                "discount": 5.00,
            }
        ],
    }

    conn = connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM bill_items WHERE bill_id = %s;", (new_bill_id,))
        cur.execute("DELETE FROM bills WHERE bill_id = %s;", (new_bill_id,))
        conn.commit()
    finally:
        conn.close()

    res = client.post("/bills/", json=payload, headers={"Authorization": f"Bearer {cashier_token}"})
    assert res.status_code == 200
    created = res.json()
    assert created["bill_id"] == new_bill_id
    assert float(created["total_amount"]) == (3 * 45.00 - 5.00)

    # Cashier can retrieve receipt
    res_get = client.get(f"/bills/{new_bill_id}", headers={"Authorization": f"Bearer {cashier_token}"})
    assert res_get.status_code == 200
    assert res_get.json()["bill"][0] == new_bill_id

    # Cashier can download receipt PDF
    res_pdf = client.get(f"/bills/{new_bill_id}/pdf", headers={"Authorization": f"Bearer {cashier_token}"})
    assert res_pdf.status_code == 200
    assert res_pdf.content.startswith(b"%PDF-1.4")
