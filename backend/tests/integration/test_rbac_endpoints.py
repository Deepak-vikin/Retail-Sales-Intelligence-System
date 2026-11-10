import os
import time
import uuid
import json
import urllib.request
import io
import concurrent.futures
from datetime import datetime
from unittest.mock import MagicMock
import jwt
from jwt import PyJWKClientError
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.main import app
from app.core.permissions import AppRole
from app.core.auth import set_jwks_client, get_jwks_client, set_employee_lookup_override
from app.api.employees import (
    set_owner_count_fn,
    set_on_owner_created_fn,
    log_audit_event,
    AuditLoggingError,
    set_audit_log_sink,
    set_mock_bootstrap_profile_fn,
    set_mock_create_employee_fn,
    set_mock_update_employee_fn,
    set_mock_auth_admin_create_fn,
    set_mock_auth_delete_fn,
    set_mock_delete_employee_fn,
    compensate_supabase_auth_user,
    EmployeeProfileResponse,
)
from app.api.system import (
    set_audit_logs_reader,
    set_ai_connectivity_check_fn,
    set_sync_runner_override,
)
from app.core.config import SUPABASE_URL
from app.core.database import get_transaction

client = TestClient(app)

TEST_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key()
TEST_KID = "6d78198a-7ebc-4949-b6f4-b0f1e1294b29"

ROTATED_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
ROTATED_PUBLIC_KEY = ROTATED_PRIVATE_KEY.public_key()
ROTATED_KID = "rotated-new-kid-2026-11"

ANOTHER_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
ANOTHER_PUBLIC_KEY = ANOTHER_PRIVATE_KEY.public_key()

TEST_EMPLOYEES = {}

class MockJWKSClient:
    def __init__(self):
        self.keys = {
            TEST_KID: TEST_PUBLIC_KEY
        }
        self.fetch_count = 0

    def add_rotated_key(self, kid: str, public_key):
        self.keys[kid] = public_key

    def get_signing_key_from_jwt(self, token: str):
        self.fetch_count += 1
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if kid not in self.keys:
            raise PyJWKClientError(f"Signing key with kid '{kid}' not found in JWKS.")
        mock_key = MagicMock()
        mock_key.key = self.keys[kid]
        return mock_key

BOOTSTRAP_TEST_SECRET = "test-high-entropy-bootstrap-secret-9999"
AUDIT_LOG_RECORDS = []

@pytest.fixture(autouse=True)
def setup_rbac_environment(monkeypatch):
    global TEST_EMPLOYEES, AUDIT_LOG_RECORDS
    TEST_EMPLOYEES = {}
    AUDIT_LOG_RECORDS = []

    # Setup mock JWKS client
    mock_jwks = MockJWKSClient()
    set_jwks_client(mock_jwks)

    # Setup DB employee lookup override
    set_employee_lookup_override(lambda uid: TEST_EMPLOYEES.get(uid))

    # Reset owner count override
    set_owner_count_fn(None)
    set_on_owner_created_fn(None)

    # Setup audit log sink to capture audit events in memory
    set_audit_log_sink(lambda actor, action, target, details: AUDIT_LOG_RECORDS.append({
        "performed_by": actor,
        "action_type": action,
        "target_resource": target,
        "details": details,
    }))

    # Setup audit logs reader for GET /system/audit-logs
    set_audit_logs_reader(lambda limit: [
        {
            "log_id": i + 1,
            "performed_by": r["performed_by"],
            "action_type": r["action_type"],
            "target_resource": r["target_resource"],
            "details": r["details"],
            "performed_at": datetime.now(),
        }
        for i, r in enumerate(AUDIT_LOG_RECORDS[-limit:])
    ])

    # Setup mock profile handlers so tests without live DB succeed while firing audit logging
    set_mock_bootstrap_profile_fn(lambda p, actor: EmployeeProfileResponse(
        id=actor or str(uuid.uuid4()),
        full_name=p.full_name,
        email=p.email,
        role=AppRole.OWNER,
        is_active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    ))

    set_mock_create_employee_fn(lambda p, user: EmployeeProfileResponse(
        id=str(uuid.uuid4()),
        full_name=p.full_name,
        email=p.email,
        role=p.role,
        is_active=p.is_active,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    ))

    set_mock_update_employee_fn(lambda emp_id, u, user: EmployeeProfileResponse(
        id=emp_id,
        full_name=u.full_name or "Updated Name",
        email="test@test.com",
        role=u.role or AppRole.MANAGER,
        is_active=u.is_active if u.is_active is not None else True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    ))

    # Mock service functions so tests don't make real PostgreSQL connections
    monkeypatch.setattr("app.Services.product_service.get_products", lambda: [{"product_id": 1, "product_name": "Test Item"}])
    monkeypatch.setattr("app.Services.purchase_service.get_all_purchases", lambda: [{"purchase_id": 1}])
    monkeypatch.setattr("app.api.analytics.get_today_revenue", lambda: {"revenue": 12500.0})
    monkeypatch.setattr("app.api.bills.get_recent_bills", lambda limit=100: [{"bill_id": 101, "payment_mode": "UPI", "total_amount": 750.0}])
    monkeypatch.setattr("app.api.bills.get_bill", lambda bill_id: {"bill_id": bill_id, "payment_mode": "UPI", "total_amount": 750.0})
    monkeypatch.setattr("app.api.employees.BOOTSTRAP_SECRET", BOOTSTRAP_TEST_SECRET)
    monkeypatch.setattr("app.api.employees.SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key-999")
    set_mock_auth_admin_create_fn(lambda p: {
        "id": str(uuid.uuid4()),
        "email": p.get("email"),
        "user_metadata": p.get("user_metadata", {})
    })
    set_mock_auth_delete_fn(lambda uid: True)
    set_mock_delete_employee_fn(lambda emp_id, user: TEST_EMPLOYEES.pop(emp_id, None))

    yield mock_jwks

    set_employee_lookup_override(None)
    set_owner_count_fn(None)
    set_on_owner_created_fn(None)
    set_audit_log_sink(None)
    set_audit_logs_reader(None)
    set_mock_bootstrap_profile_fn(None)
    set_mock_create_employee_fn(None)
    set_mock_update_employee_fn(None)
    set_mock_auth_admin_create_fn(None)
    set_mock_auth_delete_fn(None)
    set_mock_delete_employee_fn(None)
    set_ai_connectivity_check_fn(None)
    set_sync_runner_override(None)
    import app.api.system as sys_mod
    with sys_mod._sync_lock:
        sys_mod._is_sync_running = False

def make_es256_jwt(
    user_id: str,
    email: str,
    role: str,
    is_active: bool = True,
    expired: bool = False,
    kid: str = TEST_KID,
    signing_key = TEST_PRIVATE_KEY,
    issuer: str = None,
    audience: str = "authenticated",
    register_profile: bool = True,
) -> str:
    now = int(time.time())
    expected_iss = f"{SUPABASE_URL.rstrip('/')}/auth/v1"
    token_iss = issuer if issuer is not None else expected_iss

    payload = {
        "sub": user_id,
        "email": email,
        "iss": token_iss,
        "aud": audience,
        "role": "authenticated",
        "exp": now - 3600 if expired else now + 3600,
        "iat": now - 10,
        "user_metadata": {
            "full_name": f"Test {role.title()}",
            "role": role,
            "is_active": is_active,
        },
        "app_metadata": {
            "provider": "email",
            "role": role,
        }
    }

    if register_profile:
        TEST_EMPLOYEES[user_id] = {
            "id": user_id,
            "full_name": f"Test {role.title()}",
            "email": email,
            "role": role,
            "is_active": is_active,
        }

    return jwt.encode(payload, signing_key, algorithm="ES256", headers={"kid": kid})

# =========================================================================
# 1. Missing and Malformed Token Tests
# =========================================================================

def test_missing_authorization_header():
    res = client.get("/products/")
    assert res.status_code == 401
    assert "Missing Authorization header" in res.json()["detail"]

def test_malformed_token():
    res = client.get("/products/", headers={"Authorization": "Bearer invalid-token-string"})
    assert res.status_code == 401
    assert "Malformed JWT header" in res.json()["detail"]

# =========================================================================
# 2. Cryptographic Signature & Expiration Tests
# =========================================================================

def test_invalid_es256_jwt_signature():
    token = make_es256_jwt(str(uuid.uuid4()), "owner@test.com", "owner", signing_key=ANOTHER_PRIVATE_KEY)
    res = client.get("/products/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert "Invalid token signature" in res.json()["detail"]

def test_expired_es256_jwt():
    token = make_es256_jwt(str(uuid.uuid4()), "owner@test.com", "owner", expired=True)
    res = client.get("/products/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert "expired" in res.json()["detail"]

# =========================================================================
# 3. JWKS Key Rotation and Unknown Key ID Tests
# =========================================================================

def test_unknown_key_id_rejected():
    token = make_es256_jwt(str(uuid.uuid4()), "owner@test.com", "owner", kid="unknown-kid-999")
    res = client.get("/products/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert "Unknown or rotated key ID" in res.json()["detail"]

def test_jwks_key_rotation_success(setup_rbac_environment):
    mock_jwks = setup_rbac_environment
    # Add rotated key to JWKS
    mock_jwks.add_rotated_key(ROTATED_KID, ROTATED_PUBLIC_KEY)

    token = make_es256_jwt(
        str(uuid.uuid4()),
        "owner@test.com",
        "owner",
        kid=ROTATED_KID,
        signing_key=ROTATED_PRIVATE_KEY
    )
    res = client.get("/products/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

# =========================================================================
# 4. JWT Issuer & Audience Validation Tests
# =========================================================================

def test_invalid_jwt_issuer_rejected():
    token = make_es256_jwt(
        str(uuid.uuid4()),
        "owner@test.com",
        "owner",
        issuer="https://fraudulent-issuer.supabase.co/auth/v1"
    )
    res = client.get("/products/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert "Invalid token issuer" in res.json()["detail"]

def test_invalid_jwt_audience_rejected():
    token = make_es256_jwt(
        str(uuid.uuid4()),
        "owner@test.com",
        "owner",
        audience="wrong-client-app"
    )
    res = client.get("/products/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert "Invalid token audience" in res.json()["detail"]

# =========================================================================
# 5. Database-Backed Role & Inactive Employee Tests (No Self-Assignment)
# =========================================================================

def test_user_without_db_employee_profile_rejected():
    # User signs up on Supabase and puts {"role": "owner"} in user_metadata,
    # but has NOT been onboarded by the shop owner into employee_profiles.
    uid = str(uuid.uuid4())
    token = make_es256_jwt(uid, "public_user@test.com", "owner", register_profile=False)

    res = client.get("/products/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert "does not have an active employee profile" in res.json()["detail"]

def test_inactive_employee_rejected():
    token = make_es256_jwt(str(uuid.uuid4()), "inactive@test.com", "cashier", is_active=False)
    res = client.get("/products/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert "deactivated" in res.json()["detail"]

# =========================================================================
# 6. First-Owner Bootstrap Tests
# =========================================================================

def test_bootstrap_owner_missing_secret_rejected():
    res = client.post(
        "/employees/bootstrap-owner",
        json={"email": "newowner@test.com", "password": "Password123!", "full_name": "First Owner", "role": "owner"}
    )
    assert res.status_code == 403
    assert "secret" in res.json()["detail"].lower()

def test_bootstrap_owner_invalid_secret_rejected():
    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": "invalid-secret-value-1234"},
        json={"email": "newowner@test.com", "password": "Password123!", "full_name": "First Owner", "role": "owner"}
    )
    assert res.status_code == 403
    assert "Invalid bootstrap credential" in res.json()["detail"]

def test_bootstrap_owner_disabled_when_bootstrap_secret_empty(monkeypatch):
    monkeypatch.setattr("app.api.employees.BOOTSTRAP_SECRET", "")
    monkeypatch.delenv("BOOTSTRAP_SECRET", raising=False)
    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "newowner@test.com", "password": "Password123!", "full_name": "First Owner", "role": "owner"}
    )
    assert res.status_code == 403
    assert "secret configuration" in res.json()["detail"].lower()

def test_bootstrap_owner_blocked_when_owner_already_exists():
    # Simulate database already having an owner
    set_owner_count_fn(lambda: 1)

    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "secondowner@test.com", "password": "Password123!", "full_name": "Attacker Owner", "role": "owner"}
    )
    assert res.status_code == 400
    assert "Store owner already bootstrapped" in res.json()["detail"]

def test_bootstrap_owner_succeeds_when_zero_owners():
    set_owner_count_fn(lambda: 0)

    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "firstowner@test.com", "password": "Password123!", "full_name": "First Store Owner", "role": "owner"}
    )
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "firstowner@test.com"
    assert data["role"] == "owner"

def test_bootstrap_owner_role_injection_overridden_to_owner():
    # Even if client tries to supply role="cashier" or "programmer" in request body,
    # the backend MUST strictly force the role to 'owner'.
    set_owner_count_fn(lambda: 0)

    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "injected@test.com", "password": "Password123!", "full_name": "Injected Role User", "role": "cashier"}
    )
    assert res.status_code == 201
    data = res.json()
    assert data["role"] == "owner"

def test_bootstrap_owner_repeated_bootstrap_rejected():
    # Simulate state: starts at 0, transitions to 1 on creation
    owner_count = 0
    def count_fn():
        return owner_count
    def on_created():
        nonlocal owner_count
        owner_count += 1

    set_owner_count_fn(count_fn)
    set_on_owner_created_fn(on_created)

    # First attempt: succeeds (0 owners exist)
    res1 = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "owner1@test.com", "password": "Password123!", "full_name": "Owner 1", "role": "owner"}
    )
    assert res1.status_code == 201
    assert res1.json()["role"] == "owner"

    # Second attempt: permanently blocked because 1 owner now exists
    res2 = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "owner2@test.com", "password": "Password123!", "full_name": "Owner 2", "role": "owner"}
    )
    assert res2.status_code == 400
    assert "Store owner already bootstrapped" in res2.json()["detail"]

def test_bootstrap_owner_concurrent_attempts():
    # Simulate concurrent requests from multiple callers attempting to race to bootstrap
    owner_count = 0
    def count_fn():
        return owner_count
    def on_created():
        nonlocal owner_count
        owner_count += 1

    set_owner_count_fn(count_fn)
    set_on_owner_created_fn(on_created)

    def attempt_bootstrap(email_suffix):
        return client.post(
            "/employees/bootstrap-owner",
            headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
            json={
                "email": f"concurrent_{email_suffix}@test.com",
                "password": "Password123!",
                "full_name": f"Concurrent User {email_suffix}",
                "role": "owner"
            }
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(attempt_bootstrap, i) for i in range(4)]
        results = [f.result() for f in futures]

    statuses = [r.status_code for r in results]
    # Exactly one request MUST succeed with 201 Created; all 3 others MUST be rejected with 400 Bad Request
    assert statuses.count(201) == 1, f"Expected exactly 1 success, got statuses: {statuses}"
    assert statuses.count(400) == 3, f"Expected 3 rejections, got statuses: {statuses}"

def test_bootstrap_secret_never_leaked_in_response():
    set_owner_count_fn(lambda: 0)

    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "leakcheck@test.com", "password": "Password123!", "full_name": "Leak Check", "role": "owner"}
    )
    # The secret value should never appear in response body or headers
    assert BOOTSTRAP_TEST_SECRET not in res.text
    assert BOOTSTRAP_TEST_SECRET not in str(res.headers)

# =========================================================================
# 7. Audit Log Access Controls
# =========================================================================

def test_owner_can_access_audit_logs():
    token = make_es256_jwt(str(uuid.uuid4()), "owner@test.com", "owner")
    res = client.get("/system/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

def test_programmer_can_access_audit_logs():
    token = make_es256_jwt(str(uuid.uuid4()), "programmer@test.com", "programmer")
    res = client.get("/system/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

def test_manager_cannot_access_audit_logs():
    token = make_es256_jwt(str(uuid.uuid4()), "manager@test.com", "manager")
    res = client.get("/system/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403

def test_cashier_cannot_access_audit_logs():
    token = make_es256_jwt(str(uuid.uuid4()), "cashier@test.com", "cashier")
    res = client.get("/system/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403

# =========================================================================
# 8. Role Separation & Boundary Enforcement Tests
# =========================================================================

def test_owner_full_business_and_employee_management():
    token = make_es256_jwt(str(uuid.uuid4()), "owner@test.com", "owner")
    res_prod = client.get("/products/", headers={"Authorization": f"Bearer {token}"})
    assert res_prod.status_code == 200

    res_ana = client.get("/analytics/today/revenue", headers={"Authorization": f"Bearer {token}"})
    assert res_ana.status_code == 200

def test_manager_access_and_restrictions():
    token = make_es256_jwt(str(uuid.uuid4()), "manager@test.com", "manager")
    res_prod = client.get("/products/", headers={"Authorization": f"Bearer {token}"})
    assert res_prod.status_code == 200

    res_ana = client.get("/analytics/today/revenue", headers={"Authorization": f"Bearer {token}"})
    assert res_ana.status_code == 200

    res_emp = client.get("/employees/", headers={"Authorization": f"Bearer {token}"})
    assert res_emp.status_code == 403
    assert "Only shop 'owner'" in res_emp.json()["detail"]

def test_cashier_access_and_restrictions():
    token = make_es256_jwt(str(uuid.uuid4()), "cashier@test.com", "cashier")
    res_prod = client.get("/products/", headers={"Authorization": f"Bearer {token}"})
    assert res_prod.status_code == 200

    res_ana = client.get("/analytics/today/revenue", headers={"Authorization": f"Bearer {token}"})
    assert res_ana.status_code == 403

    res_emp = client.get("/employees/", headers={"Authorization": f"Bearer {token}"})
    assert res_emp.status_code == 403

def test_programmer_restrictions_and_health_access():
    token = make_es256_jwt(str(uuid.uuid4()), "tech@test.com", "programmer")
    res_health = client.get("/system/health", headers={"Authorization": f"Bearer {token}"})
    assert res_health.status_code == 200
    assert res_health.json()["roles_supported"] == ["owner", "manager", "cashier", "programmer"]

    res_ana = client.get("/analytics/today/revenue", headers={"Authorization": f"Bearer {token}"})
    assert res_ana.status_code == 403

    res_pur = client.get("/purchases/", headers={"Authorization": f"Bearer {token}"})
    assert res_pur.status_code == 403

    res_emp = client.get("/employees/", headers={"Authorization": f"Bearer {token}"})
    assert res_emp.status_code == 403

def test_employee_role_escalation_attempt_rejected():
    token = make_es256_jwt(str(uuid.uuid4()), "manager@test.com", "manager")
    res = client.patch(
        f"/employees/{str(uuid.uuid4())}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "owner"}
    )
    assert res.status_code == 403

def test_legacy_hs256_token_behavior():
    now = int(time.time())
    token = jwt.encode({
        "sub": str(uuid.uuid4()),
        "email": "legacy@test.com",
        "iss": f"{SUPABASE_URL.rstrip('/')}/auth/v1",
        "aud": "authenticated",
        "exp": now + 3600,
        "user_metadata": {"role": "cashier"}
    }, "legacy-secret-key-at-least-32-bytes!!", algorithm="HS256")

    res = client.get("/products/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401

# =========================================================================
# 9. Hardened UUID-Based Audit Logging Tests
# =========================================================================

def test_audit_event_valid_authenticated_uuid_recorded():
    actor_uuid = str(uuid.uuid4())
    log_audit_event(
        performed_by=actor_uuid,
        action_type="TEST_ACTION",
        target_resource="target@test.com",
        details="Valid UUID audit event"
    )
    assert len(AUDIT_LOG_RECORDS) > 0
    assert AUDIT_LOG_RECORDS[-1]["performed_by"] == actor_uuid
    assert AUDIT_LOG_RECORDS[-1]["action_type"] == "TEST_ACTION"

def test_audit_event_none_accepted_for_system_actions():
    log_audit_event(
        performed_by=None,
        action_type="SYSTEM_MAINTENANCE",
        target_resource="system_db",
        details="System-generated background maintenance"
    )
    assert len(AUDIT_LOG_RECORDS) > 0
    assert AUDIT_LOG_RECORDS[-1]["performed_by"] is None
    assert AUDIT_LOG_RECORDS[-1]["action_type"] == "SYSTEM_MAINTENANCE"

def test_audit_event_rejects_arbitrary_strings_system_and_admin():
    # Attempting to pass non-UUID strings must raise ValueError immediately
    with pytest.raises(ValueError, match="Arbitrary actor strings such as 'system' or 'admin' are not permitted"):
        log_audit_event(performed_by="system", action_type="INVALID_ACTOR")

    with pytest.raises(ValueError, match="Arbitrary actor strings such as 'system' or 'admin' are not permitted"):
        log_audit_event(performed_by="admin", action_type="INVALID_ACTOR")

    with pytest.raises(ValueError, match="Invalid UUID format"):
        log_audit_event(performed_by="not-a-valid-uuid-string", action_type="INVALID_ACTOR")

def test_bootstrap_missing_service_role_key_rejected(monkeypatch):
    monkeypatch.setattr("app.api.employees.SUPABASE_SERVICE_ROLE_KEY", "")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    set_owner_count_fn(lambda: 0)

    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "noservicekey@test.com", "password": "Password123!", "full_name": "No Service Key", "role": "owner"}
    )
    assert res.status_code == 500
    assert "SUPABASE_SERVICE_ROLE_KEY" in res.json()["detail"]


def test_bootstrap_failed_admin_api_provisioning_aborts(monkeypatch):
    set_mock_auth_admin_create_fn(None)

    def mock_urlopen_fail(req, timeout=10):
        raise urllib.error.URLError("Network unreachable")

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen_fail)
    set_owner_count_fn(lambda: 0)

    audit_count_before = len(AUDIT_LOG_RECORDS)
    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "failedadmin@test.com", "password": "Password123!", "full_name": "Failed Admin", "role": "owner"}
    )
    # Must abort immediately with 502; never proceed with local/fabricated UUID
    assert res.status_code == 502
    assert "Failed to create owner identity in Supabase Auth" in res.json()["detail"]
    assert len(AUDIT_LOG_RECORDS) == audit_count_before


def test_bootstrap_missing_returned_user_id_aborts():
    # Admin API returned 200 but response has no valid user ID
    set_mock_auth_admin_create_fn(lambda p: {"error": "user_already_exists"})
    set_owner_count_fn(lambda: 0)

    audit_count_before = len(AUDIT_LOG_RECORDS)
    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "noid@test.com", "password": "Password123!", "full_name": "No ID Returned", "role": "owner"}
    )
    # Must abort immediately with 502
    assert res.status_code == 502
    assert "no valid user ID returned" in res.json()["detail"]
    assert len(AUDIT_LOG_RECORDS) == audit_count_before


def test_bootstrap_with_successful_supabase_auth_creation(monkeypatch):
    confirmed_id = "6d78198a-7ebc-4949-b6f4-b0f1e1294b29"
    set_mock_auth_admin_create_fn(None)

    def mock_urlopen_success(req, timeout=10):
        resp = MagicMock()
        resp.read.return_value = json.dumps({"id": confirmed_id}).encode("utf-8")
        resp.__enter__.return_value = resp
        return resp

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen_success)
    set_owner_count_fn(lambda: 0)

    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "confirmedowner@test.com", "password": "Password123!", "full_name": "Confirmed Owner", "role": "owner"}
    )
    assert res.status_code == 201
    assert res.json()["id"] == confirmed_id
    bootstrap_audit = [r for r in AUDIT_LOG_RECORDS if r["action_type"] == "BOOTSTRAP_OWNER_CREATED"][-1]
    # Must use the confirmed Supabase user UUID
    assert bootstrap_audit["performed_by"] == confirmed_id


def test_bootstrap_never_inserts_fabricated_uuid(monkeypatch):
    # When Auth user creation fails, the endpoint must abort with 502
    # and NEVER insert a fabricated UUID or proceed to database insertion.
    set_mock_auth_admin_create_fn(None)

    def mock_urlopen_fail(req, timeout=10):
        raise urllib.error.URLError("Network down")

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen_fail)
    set_owner_count_fn(lambda: 0)

    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "nofabricated@test.com", "password": "Password123!", "full_name": "No Fabricated UUID", "role": "owner"}
    )
    assert res.status_code == 502
    # Confirms no 201 was returned and no fabricated UUID profile was created
    assert res.status_code != 201

def test_audit_database_failure_not_silently_ignored():
    # Configure audit log sink to simulate database insertion failure
    def mock_failing_audit_sink(actor, action, target, details):
        raise AuditLoggingError("Simulated database failure: connection refused")

    set_audit_log_sink(mock_failing_audit_sink)
    set_owner_count_fn(lambda: 0)

    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "auditfail@test.com", "password": "Password123!", "full_name": "Audit Failure Test", "role": "owner"}
    )
    # The operation MUST NOT report success when the audit operation has failed
    assert res.status_code == 500
    assert "Security audit logging failed" in res.json()["detail"]

def test_audit_log_retrieval_with_null_actor():
    # Inject a system audit record with performed_by = None
    AUDIT_LOG_RECORDS.append({
        "performed_by": None,
        "action_type": "BOOTSTRAP_OWNER_CREATED",
        "target_resource": "bootstrap@retail.com",
        "details": "Bootstrap without pre-existing auth actor"
    })

    token = make_es256_jwt(str(uuid.uuid4()), "owner@test.com", "owner")
    res = client.get("/system/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    logs = res.json()
    # Verify records with performed_by = None are returned safely without error
    null_actor_logs = [l for l in logs if l["performed_by"] is None]
    assert len(null_actor_logs) > 0
    assert null_actor_logs[0]["action_type"] == "BOOTSTRAP_OWNER_CREATED"

def test_existing_employee_creation_and_role_update_audit_intact():
    owner_uid = str(uuid.uuid4())
    token = make_es256_jwt(owner_uid, "owner@test.com", "owner")

    # 1. Employee Creation
    res_create = client.post(
        "/employees/",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "staff1@test.com", "password": "Password123!", "full_name": "Staff One", "role": "cashier"}
    )
    assert res_create.status_code == 201
    create_audits = [r for r in AUDIT_LOG_RECORDS if r["action_type"] == "EMPLOYEE_CREATED"]
    assert len(create_audits) > 0
    assert create_audits[-1]["performed_by"] == owner_uid
    assert create_audits[-1]["target_resource"] == res_create.json()["id"]
    assert "staff1@test.com" not in create_audits[-1]["target_resource"]

    # 2. Employee Role Update
    created_emp_id = res_create.json()["id"]
    res_update = client.patch(
        f"/employees/{created_emp_id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "manager"}
    )
    assert res_update.status_code == 200
    update_audits = [r for r in AUDIT_LOG_RECORDS if r["action_type"] == "EMPLOYEE_UPDATED"]
    assert len(update_audits) > 0
    assert update_audits[-1]["performed_by"] == owner_uid
    assert update_audits[-1]["target_resource"] == created_emp_id


# ============================================================================
# SECTION 10: TRANSACTION LIFECYCLE, ROLLBACK, & SUPABASE AUTH COMPENSATION
# ============================================================================

def test_successful_employee_creation_with_auth_and_no_compensation():
    owner_uid = str(uuid.uuid4())
    token = make_es256_jwt(owner_uid, "owner@test.com", "owner")

    created_auth_id = str(uuid.uuid4())
    compensated_ids = []

    set_mock_auth_admin_create_fn(lambda p: {"id": created_auth_id, "email": p["email"]})
    set_mock_auth_delete_fn(lambda uid: (compensated_ids.append(uid), True)[1])

    res = client.post(
        "/employees/",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "goodstaff@test.com", "password": "Password123!", "full_name": "Good Staff", "role": "cashier"}
    )
    assert res.status_code == 201
    assert len(compensated_ids) == 0  # No compensation triggered on success


def test_employee_profile_insertion_failure_after_auth_creation():
    owner_uid = str(uuid.uuid4())
    token = make_es256_jwt(owner_uid, "owner@test.com", "owner")

    created_auth_id = str(uuid.uuid4())
    compensated_ids = []

    set_mock_auth_admin_create_fn(lambda p: {"id": created_auth_id, "email": p["email"]})
    set_mock_auth_delete_fn(lambda uid: (compensated_ids.append(uid), True)[1])

    # Simulate DB profile failure after auth creation
    def failing_profile_create(profile, user):
        raise RuntimeError("Simulated DB employee profile insert constraint failure")

    set_mock_create_employee_fn(failing_profile_create)

    res = client.post(
        "/employees/",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "failprofile@test.com", "password": "Password123!", "full_name": "Fail Profile", "role": "cashier"}
    )
    assert res.status_code == 500
    assert created_auth_id in compensated_ids  # Supabase Auth user was compensated/deleted


def test_employee_audit_insertion_failure_after_auth_creation():
    owner_uid = str(uuid.uuid4())
    token = make_es256_jwt(owner_uid, "owner@test.com", "owner")

    created_auth_id = str(uuid.uuid4())
    compensated_ids = []

    set_mock_auth_admin_create_fn(lambda p: {"id": created_auth_id, "email": p["email"]})
    set_mock_auth_delete_fn(lambda uid: (compensated_ids.append(uid), True)[1])

    # Audit fails
    def failing_audit(actor, action, target, details):
        raise AuditLoggingError("Simulated disk error during audit recording")

    set_audit_log_sink(failing_audit)

    res = client.post(
        "/employees/",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "failaudit@test.com", "password": "Password123!", "full_name": "Fail Audit", "role": "cashier"}
    )
    assert res.status_code == 500
    assert created_auth_id in compensated_ids  # Compensation was triggered on audit failure


def test_successful_compensation_deletion_helper():
    test_user_id = str(uuid.uuid4())
    deleted_ids = []
    set_mock_auth_delete_fn(lambda uid: (deleted_ids.append(uid), True)[1])

    # Case: created_by_this_request = True -> should delete
    result = compensate_supabase_auth_user(test_user_id, created_by_this_request=True)
    assert result is True
    assert test_user_id in deleted_ids


def test_compensation_deletion_failure():
    owner_uid = str(uuid.uuid4())
    token = make_es256_jwt(owner_uid, "owner@test.com", "owner")

    created_auth_id = str(uuid.uuid4())
    set_mock_auth_admin_create_fn(lambda p: {"id": created_auth_id, "email": p["email"]})

    # Delete compensation fails (e.g. Supabase Admin API returns 500)
    set_mock_auth_delete_fn(lambda uid: False)

    def failing_audit(actor, action, target, details):
        raise AuditLoggingError("Audit write failure")

    set_audit_log_sink(failing_audit)

    res = client.post(
        "/employees/",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "compfail@test.com", "password": "Password123!", "full_name": "Comp Fail", "role": "cashier"}
    )
    assert res.status_code == 500
    detail = res.json()["detail"].lower()
    assert "compensation failed" in detail or "rollback failed" in detail


def test_existing_auth_users_are_never_deleted():
    existing_user_id = str(uuid.uuid4())
    deleted_ids = []
    set_mock_auth_delete_fn(lambda uid: (deleted_ids.append(uid), True)[1])

    # Case: created_by_this_request = False -> must NEVER delete
    result = compensate_supabase_auth_user(existing_user_id, created_by_this_request=False)
    assert result is True
    assert len(deleted_ids) == 0  # Not deleted!

    # Case: None user_id -> must NEVER delete
    result_none = compensate_supabase_auth_user(None, created_by_this_request=True)
    assert result_none is True
    assert len(deleted_ids) == 0


def test_successful_bootstrap_with_auth_and_audit():
    owner_auth_id = str(uuid.uuid4())
    compensated_ids = []

    set_owner_count_fn(lambda: 0)
    set_mock_auth_admin_create_fn(lambda p: {"id": owner_auth_id, "email": p["email"]})
    set_mock_auth_delete_fn(lambda uid: (compensated_ids.append(uid), True)[1])

    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "bootstrap_success@test.com", "password": "Password123!", "full_name": "Success Owner", "role": "owner"}
    )
    assert res.status_code == 201
    assert len(compensated_ids) == 0  # No compensation on success


def test_bootstrap_audit_failure_and_auth_compensation():
    owner_auth_id = str(uuid.uuid4())
    compensated_ids = []

    set_owner_count_fn(lambda: 0)
    set_mock_auth_admin_create_fn(lambda p: {"id": owner_auth_id, "email": p["email"]})
    set_mock_auth_delete_fn(lambda uid: (compensated_ids.append(uid), True)[1])

    def failing_audit(actor, action, target, details):
        raise AuditLoggingError("Audit failure during bootstrap")

    set_audit_log_sink(failing_audit)

    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "bootstrap_audit_fail@test.com", "password": "Password123!", "full_name": "Fail Owner", "role": "owner"}
    )
    assert res.status_code == 500
    assert owner_auth_id in compensated_ids  # The newly created Auth user was compensated


def test_explicit_postgresql_rollback_on_failure(monkeypatch):
    owner_uid = str(uuid.uuid4())
    token = make_es256_jwt(owner_uid, "owner@test.com", "owner")

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = (owner_uid, "Test Name", "test@retail.com", "manager", True, datetime.now(), datetime.now())

    monkeypatch.setattr("app.api.employees.connection", lambda: mock_conn)

    # Make audit logging fail inside update_employee_role
    def failing_audit(performed_by, action_type, target_resource=None, details=None, cur=None):
        raise AuditLoggingError("Simulated audit DB insert failure")

    monkeypatch.setattr("app.api.employees.log_audit_event", failing_audit)

    res = client.patch(
        f"/employees/{owner_uid}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "cashier"}
    )
    assert res.status_code == 500
    mock_conn.rollback.assert_called()  # Explicit rollback was called
    mock_conn.commit.assert_not_called()  # Commit was not called


def test_connection_and_cursor_cleanup(monkeypatch):
    owner_uid = str(uuid.uuid4())
    token = make_es256_jwt(owner_uid, "owner@test.com", "owner")

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = (owner_uid, "Test Name", "test@retail.com", "manager", True, datetime.now(), datetime.now())

    monkeypatch.setattr("app.api.employees.connection", lambda: mock_conn)
    monkeypatch.setattr("app.api.employees.log_audit_event", lambda **kwargs: None)

    # 1. Success path
    res = client.patch(
        f"/employees/{owner_uid}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "cashier"}
    )
    assert res.status_code == 200
    mock_cur.close.assert_called()
    mock_conn.close.assert_called()

    # 2. Failure path
    mock_cur.reset_mock()
    mock_conn.reset_mock()
    mock_conn.cursor.return_value = mock_cur

    def failing_audit(performed_by, action_type, target_resource=None, details=None, cur=None):
        raise AuditLoggingError("Audit failure")

    monkeypatch.setattr("app.api.employees.log_audit_event", failing_audit)

    res_fail = client.patch(
        f"/employees/{owner_uid}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "cashier"}
    )
    assert res_fail.status_code == 500
    mock_cur.close.assert_called()
    mock_conn.close.assert_called()


def test_database_get_transaction_context_manager():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur

    # Success scenario: commits and closes
    with get_transaction(conn=mock_conn) as (c, cur):
        assert c == mock_conn
        assert cur == mock_cur
    mock_conn.commit.assert_called_once()
    mock_cur.close.assert_called_once()

    # Exception scenario: rolls back and closes
    mock_conn.reset_mock()
    mock_cur.reset_mock()
    mock_conn.cursor.return_value = mock_cur

    with pytest.raises(ValueError):
        with get_transaction(conn=mock_conn) as (c, cur):
            raise ValueError("Simulated operation error")
    mock_conn.rollback.assert_called_once()
    mock_conn.commit.assert_not_called()
    mock_cur.close.assert_called_once()


# ============================================================================
# SECTION 11: OWNER EMPLOYEE MANAGEMENT & NON-OWNER RESTRICTION TESTS
# ============================================================================

def test_owner_can_create_another_owner_independent_of_bootstrap_secret(monkeypatch):
    """
    Verifies that:
    1. An authenticated owner can create another owner via POST /employees/.
    2. The endpoint works when BOOTSTRAP_SECRET is removed/empty.
    3. Audit logging records EMPLOYEE_CREATED with performed_by as owner UUID.
    """
    monkeypatch.setattr("app.api.employees.BOOTSTRAP_SECRET", "")
    monkeypatch.delenv("BOOTSTRAP_SECRET", raising=False)

    owner_uid = str(uuid.uuid4())
    token = make_es256_jwt(owner_uid, "primary_owner@store.com", "owner")

    new_owner_auth_id = str(uuid.uuid4())
    set_mock_auth_admin_create_fn(lambda p: {"id": new_owner_auth_id, "email": p["email"]})
    set_mock_create_employee_fn(lambda p, u: EmployeeProfileResponse(
        id=new_owner_auth_id,
        full_name=p.full_name,
        email=p.email,
        role=p.role,
        is_active=p.is_active,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    ))

    try:
        res = client.post(
            "/employees/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "co_owner@store.com",
                "password": "SecurePassword123!",
                "full_name": "Co-Owner User",
                "role": "owner",
                "is_active": True,
            }
        )
        assert res.status_code == 201
        data = res.json()
        assert data["role"] == "owner"
        assert data["email"] == "co_owner@store.com"

        # Verify audit trail: target_resource must record employee UUID, not email
        create_audits = [r for r in AUDIT_LOG_RECORDS if r["action_type"] == "EMPLOYEE_CREATED" and r["target_resource"] == new_owner_auth_id]
        assert len(create_audits) == 1
        assert create_audits[0]["performed_by"] == owner_uid
        assert "co_owner@store.com" not in create_audits[0]["target_resource"]
        assert "owner" in create_audits[0]["details"]
    finally:
        set_mock_auth_admin_create_fn(None)
        set_mock_create_employee_fn(None)

def test_owner_can_create_all_application_roles():
    """
    Verifies that an owner can create employees with manager, cashier, and programmer roles.
    """
    owner_uid = str(uuid.uuid4())
    token = make_es256_jwt(owner_uid, "owner@store.com", "owner")

    for role_name in ["manager", "cashier", "programmer"]:
        emp_auth_id = str(uuid.uuid4())
        set_mock_auth_admin_create_fn(lambda p, aid=emp_auth_id: {"id": aid, "email": p["email"]})
        set_mock_create_employee_fn(lambda p, u, aid=emp_auth_id: EmployeeProfileResponse(
            id=aid,
            full_name=p.full_name,
            email=p.email,
            role=p.role,
            is_active=p.is_active,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ))
        try:
            res = client.post(
                "/employees/",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "email": f"{role_name}.staff@store.com",
                    "password": "SecurePassword123!",
                    "full_name": f"{role_name.capitalize()} Staff",
                    "role": role_name,
                    "is_active": True,
                }
            )
            assert res.status_code == 201
            assert res.json()["role"] == role_name
        finally:
            set_mock_auth_admin_create_fn(None)
            set_mock_create_employee_fn(None)

def test_non_owner_roles_cannot_create_employees():
    """
    Verifies that managers, cashiers, and programmers cannot create employees (HTTP 403).
    """
    for non_owner_role in ["manager", "cashier", "programmer"]:
        user_uid = str(uuid.uuid4())
        token = make_es256_jwt(user_uid, f"{non_owner_role}@store.com", non_owner_role)

        res = client.post(
            "/employees/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": f"unauthorized.by.{non_owner_role}@store.com",
                "password": "SecurePassword123!",
                "full_name": "Unauthorized Attempt",
                "role": "cashier",
                "is_active": True,
            }
        )
        assert res.status_code == 403
        assert "Only shop 'owner'" in res.json()["detail"]

def test_non_owner_roles_cannot_update_employee_roles():
    """
    Verifies that cashiers and programmers cannot update employee roles (HTTP 403).
    """
    for non_owner_role in ["cashier", "programmer"]:
        user_uid = str(uuid.uuid4())
        token = make_es256_jwt(user_uid, f"{non_owner_role}@store.com", non_owner_role)

        target_emp_id = str(uuid.uuid4())
        res = client.patch(
            f"/employees/{target_emp_id}/role",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "manager"}
        )
        assert res.status_code == 403
        assert "Only shop 'owner'" in res.json()["detail"]

def test_owner_get_me_profile_lookup():
    """
    Verifies that an owner can access GET /employees/me, returning their profile and permissions.
    """
    owner_uid = str(uuid.uuid4())
    token = make_es256_jwt(owner_uid, "shop_owner@store.com", "owner")

    res = client.get("/employees/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["user_id"] == owner_uid
    assert data["role"] == "owner"
    assert data["is_business_user"] is True
    assert data["is_technical_user"] is False
    assert "employees:manage" in data["permissions"]
    assert "audit_logs:view" in data["permissions"]
    assert "system:health_monitor" in data["permissions"]

# =========================================================================
# 12. Phase 1 RBAC Improvements & PII Protection Tests
# =========================================================================

def test_owner_can_access_system_health():
    """
    Verifies that an owner has SYSTEM_HEALTH_MONITOR permission and can access GET /system/health.
    """
    owner_uid = str(uuid.uuid4())
    token = make_es256_jwt(owner_uid, "shop_owner@store.com", "owner")

    res = client.get("/system/health", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "roles_supported" in data
    assert "owner" in data["roles_supported"]

def test_manager_denied_access_to_system_health():
    """
    Verifies that a manager does not possess SYSTEM_HEALTH_MONITOR and is denied GET /system/health (HTTP 403).
    """
    manager_uid = str(uuid.uuid4())
    token = make_es256_jwt(manager_uid, "store_manager@store.com", "manager")

    res = client.get("/system/health", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert "lacks required permission 'system:health_monitor'" in res.json()["detail"]

def test_cashier_denied_access_to_bills_ledger():
    """
    Verifies that cashiers cannot access the store-wide historical sales ledger GET /bills/ (HTTP 403).
    """
    cashier_uid = str(uuid.uuid4())
    token = make_es256_jwt(cashier_uid, "front_cashier@store.com", "cashier")

    res = client.get("/bills/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert "lacks required permission 'billing:manage'" in res.json()["detail"]

def test_cashier_permitted_access_to_individual_receipt():
    """
    Verifies that cashiers retain permission to retrieve a single authorized receipt GET /bills/{bill_id}.
    """
    cashier_uid = str(uuid.uuid4())
    token = make_es256_jwt(cashier_uid, "front_cashier@store.com", "cashier")

    res = client.get("/bills/101", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["bill_id"] == 101
    assert data["payment_mode"] == "UPI"

def test_owner_and_manager_permitted_access_to_bills_ledger():
    """
    Verifies that both owners and managers retain permission to query GET /bills/.
    """
    for role_name in ["owner", "manager"]:
        uid = str(uuid.uuid4())
        token = make_es256_jwt(uid, f"{role_name}@store.com", role_name)

        res = client.get("/bills/", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert isinstance(res.json(), list)

def test_programmer_cannot_retrieve_employee_pii_through_audit_logs():
    """
    Verifies that technical users (programmers) cannot retrieve employee emails or PII via GET /system/audit-logs.
    """
    target_email = "sensitive.cashier@store.com"
    details_with_email = "Registered employee profile for john.doe@retail.com with initial verification"

    AUDIT_LOG_RECORDS.append({
        "performed_by": str(uuid.uuid4()),
        "action_type": "EMPLOYEE_CREATED",
        "target_resource": target_email,
        "details": details_with_email,
    })

    prog_uid = str(uuid.uuid4())
    prog_token = make_es256_jwt(prog_uid, "dev_ops@store.com", "programmer")

    res = client.get("/system/audit-logs", headers={"Authorization": f"Bearer {prog_token}"})
    assert res.status_code == 200
    response_text = res.text

    # Assert no raw email appears in programmer response
    assert target_email not in response_text
    assert "john.doe@retail.com" not in response_text

    # Assert sanitized placeholders are present
    prog_data = res.json()
    matching = [item for item in prog_data if item["action_type"] == "EMPLOYEE_CREATED"]
    assert len(matching) > 0
    assert matching[-1]["target_resource"] == "[REDACTED_EMAIL]"
    assert "[REDACTED_EMAIL]" in matching[-1]["details"]

    # Owner can view audit logs without redaction
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "shop_owner@store.com", "owner")
    owner_res = client.get("/system/audit-logs", headers={"Authorization": f"Bearer {owner_token}"})
    assert owner_res.status_code == 200
    owner_data = owner_res.json()
    owner_matching = [item for item in owner_data if item["action_type"] == "EMPLOYEE_CREATED"]
    assert owner_matching[-1]["target_resource"] == target_email

def test_employee_creation_audit_log_stores_uuid_not_email():
    """
    Verifies that employee creation logs the employee UUID in target_resource, not an email address.
    """
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "shop_owner@store.com", "owner")

    created_email = f"cashier.{uuid.uuid4().hex[:6]}@store.com"
    res = client.post(
        "/employees/",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": created_email,
            "password": "SecurePassword123!",
            "full_name": "New Cashier",
            "role": "cashier",
            "is_active": True,
        }
    )
    assert res.status_code == 201
    created_id = res.json()["id"]

    # Check last audit log record
    last_log = AUDIT_LOG_RECORDS[-1]
    assert last_log["action_type"] == "EMPLOYEE_CREATED"
    assert last_log["target_resource"] == created_id
    assert created_email not in last_log["target_resource"]
    # Ensure target_resource is a valid UUID
    uuid.UUID(last_log["target_resource"])

def test_owner_retains_employee_management_access():
    """
    Verifies owner can list, create, and update employees.
    """
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "shop_owner@store.com", "owner")

    # 1. List employees
    res_list = client.get("/employees/", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_list.status_code == 200

    # 2. Create employee
    res_create = client.post(
        "/employees/",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": f"worker.{uuid.uuid4().hex[:6]}@store.com",
            "password": "SecurePassword123!",
            "full_name": "Store Worker",
            "role": "cashier",
            "is_active": True,
        }
    )
    assert res_create.status_code == 201

    # 3. Update employee
    emp_id = res_create.json()["id"]
    res_update = client.patch(
        f"/employees/{emp_id}/role",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"role": "manager", "is_active": True}
    )
    assert res_update.status_code == 200
    assert res_update.json()["role"] == "manager"

def test_manager_cashier_programmer_denied_employee_management():
    """
    Verifies that manager, cashier, and programmer remain strictly denied from all employee-management endpoints.
    """
    for role_name in ["manager", "cashier", "programmer"]:
        uid = str(uuid.uuid4())
        token = make_es256_jwt(uid, f"{role_name}@store.com", role_name)

        # GET /employees/
        res_list = client.get("/employees/", headers={"Authorization": f"Bearer {token}"})
        assert res_list.status_code == 403
        assert "Only shop 'owner'" in res_list.json()["detail"]

        # POST /employees/
        res_create = client.post(
            "/employees/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": f"hacked.{role_name}@store.com",
                "password": "Password123!",
                "full_name": "Intruder",
                "role": "cashier",
                "is_active": True,
            }
        )
        assert res_create.status_code == 403
        assert "Only shop 'owner'" in res_create.json()["detail"]

        # PATCH /employees/{id}/role
        target_id = str(uuid.uuid4())
        res_patch = client.patch(
            f"/employees/{target_id}/role",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "owner"}
        )
        assert res_patch.status_code == 403
        assert "Only shop 'owner'" in res_patch.json()["detail"]

def test_employee_creation_validation_rules():
    """
    Verifies that POST /employees/ strictly validates passwords, emails, and roles.
    """
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.validation@store.com", "owner")

    # Password less than 8 characters
    res_short_pwd = client.post(
        "/employees/",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": "shortpwd@store.com",
            "password": "short",
            "full_name": "Short Pwd",
            "role": "cashier",
            "is_active": True
        }
    )
    assert res_short_pwd.status_code == 422

    # Invalid role
    res_bad_role = client.post(
        "/employees/",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": "badrole@store.com",
            "password": "ValidPassword123!",
            "full_name": "Bad Role",
            "role": "superadmin",
            "is_active": True
        }
    )
    assert res_bad_role.status_code == 422

    # Invalid email (less than min_length=5)
    res_bad_email = client.post(
        "/employees/",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": "a@b",
            "password": "ValidPassword123!",
            "full_name": "Bad Email",
            "role": "cashier",
            "is_active": True
        }
    )
    assert res_bad_email.status_code == 422

def test_employee_role_update_and_status_toggle_workflow():
    """
    Verifies that PATCH /employees/{id}/role updates roles and toggles is_active status.
    """
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.manage@store.com", "owner")
    target_emp_id = str(uuid.uuid4())

    # Role update to manager
    res_role = client.patch(
        f"/employees/{target_emp_id}/role",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"role": "manager"}
    )
    assert res_role.status_code == 200
    assert res_role.json()["role"] == "manager"

    # Status toggle to deactivated
    res_deact = client.patch(
        f"/employees/{target_emp_id}/role",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"is_active": False}
    )
    assert res_deact.status_code == 200
    assert res_deact.json()["is_active"] is False

    # Status toggle to activated
    res_act = client.patch(
        f"/employees/{target_emp_id}/role",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"is_active": True}
    )
    assert res_act.status_code == 200
    assert res_act.json()["is_active"] is True

# =========================================================================
# Phase 3B: System Maintenance Telemetry & Sync Trigger Integration Tests
# =========================================================================

def test_system_ai_status_permissions_and_schema():
    """
    Verifies GET /system/ai-status:
    - Owner and Programmer permitted (200 OK)
    - Manager and Cashier denied (403 Forbidden)
    - Unauthenticated denied (401)
    - Schema validation, model hierarchy, and zero secret leakage
    - Distinction between configured status and actual provider connectivity
    """
    owner_token = make_es256_jwt(str(uuid.uuid4()), "owner.ai@store.com", "owner")
    prog_token = make_es256_jwt(str(uuid.uuid4()), "prog.ai@store.com", "programmer")
    mgr_token = make_es256_jwt(str(uuid.uuid4()), "mgr.ai@store.com", "manager")
    cash_token = make_es256_jwt(str(uuid.uuid4()), "cash.ai@store.com", "cashier")

    # Manager and Cashier denied
    res_mgr = client.get("/system/ai-status", headers={"Authorization": f"Bearer {mgr_token}"})
    assert res_mgr.status_code == 403

    res_cash = client.get("/system/ai-status", headers={"Authorization": f"Bearer {cash_token}"})
    assert res_cash.status_code == 403

    # Unauthenticated denied
    res_unauth = client.get("/system/ai-status")
    assert res_unauth.status_code == 401

    # Owner access & response schema
    res_owner = client.get("/system/ai-status", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_owner.status_code == 200
    data_owner = res_owner.json()
    assert data_owner["provider"] == "OpenRouter"
    assert isinstance(data_owner["is_configured"], bool)
    assert isinstance(data_owner["all_models"], list)
    assert len(data_owner["all_models"]) >= 1
    assert data_owner["fallback_count"] == len(data_owner["fallback_models"])
    assert data_owner["status"] in ["configured", "unconfigured", "operational", "unreachable"]
    assert "OPENROUTER_API_KEY" not in res_owner.text
    assert "sk-or-" not in res_owner.text

    # Programmer access
    res_prog = client.get("/system/ai-status", headers={"Authorization": f"Bearer {prog_token}"})
    assert res_prog.status_code == 200

    # Distinguish configured status from connectivity (operational when reachable)
    set_ai_connectivity_check_fn(lambda: True)
    res_conn_true = client.get(
        "/system/ai-status?check_connectivity=true",
        headers={"Authorization": f"Bearer {prog_token}"}
    )
    assert res_conn_true.status_code == 200
    data_true = res_conn_true.json()
    assert data_true["provider_reachable"] is True
    assert data_true["status"] == "operational"

    # Distinguish configured status from connectivity (unreachable when connectivity fails)
    set_ai_connectivity_check_fn(lambda: False)
    res_conn_false = client.get(
        "/system/ai-status?check_connectivity=true",
        headers={"Authorization": f"Bearer {prog_token}"}
    )
    assert res_conn_false.status_code == 200
    data_false = res_conn_false.json()
    assert data_false["provider_reachable"] is False
    assert data_false["status"] == "unreachable"

def test_system_sync_status_permissions_and_schema():
    """
    Verifies GET /system/sync/status:
    - Owner and Programmer permitted (200 OK)
    - Manager and Cashier denied (403 Forbidden)
    - Queue metrics validation (pending, processed, rejected counts)
    - Never exposes sensitive filesystem paths or file contents
    """
    owner_token = make_es256_jwt(str(uuid.uuid4()), "owner.sync@store.com", "owner")
    prog_token = make_es256_jwt(str(uuid.uuid4()), "prog.sync@store.com", "programmer")
    mgr_token = make_es256_jwt(str(uuid.uuid4()), "mgr.sync@store.com", "manager")
    cash_token = make_es256_jwt(str(uuid.uuid4()), "cash.sync@store.com", "cashier")

    # Manager and Cashier denied
    assert client.get("/system/sync/status", headers={"Authorization": f"Bearer {mgr_token}"}).status_code == 403
    assert client.get("/system/sync/status", headers={"Authorization": f"Bearer {cash_token}"}).status_code == 403

    # Owner access & schema
    res = client.get("/system/sync/status", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 200
    data = res.json()
    assert "queue" in data
    queue = data["queue"]
    for field in [
        "pending_sales", "pending_purchases",
        "processed_sales", "processed_purchases",
        "rejected_sales", "rejected_purchases",
        "total_pending", "total_processed", "total_rejected"
    ]:
        assert field in queue
        assert isinstance(queue[field], int)
        assert queue[field] >= 0
    assert "status" in data
    assert isinstance(data["is_syncing"], bool)

    # Programmer access
    assert client.get("/system/sync/status", headers={"Authorization": f"Bearer {prog_token}"}).status_code == 200

def test_system_sync_status_handles_missing_directories(monkeypatch):
    """
    Verifies that GET /system/sync/status gracefully handles non-existent or deleted directories
    without crashing (returns 0 counts).
    """
    owner_token = make_es256_jwt(str(uuid.uuid4()), "owner.missingdir@store.com", "owner")
    from pathlib import Path
    import app.api.system as sys_mod
    monkeypatch.setattr(sys_mod, "_get_base_data_path", lambda: Path("/non_existent_data_directory_xyz_123"))

    res = client.get("/system/sync/status", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 200
    queue = res.json()["queue"]
    assert queue["total_pending"] == 0
    assert queue["total_processed"] == 0
    assert queue["total_rejected"] == 0

def test_system_sync_trigger_permissions():
    """
    Verifies POST /system/sync/trigger permissions:
    - Owner and Programmer authorized (202 Accepted)
    - Manager and Cashier denied (403 Forbidden)
    - Unauthenticated denied (401 Unauthorized)
    """
    owner_token = make_es256_jwt(str(uuid.uuid4()), "owner.trigger@store.com", "owner")
    prog_token = make_es256_jwt(str(uuid.uuid4()), "prog.trigger@store.com", "programmer")
    mgr_token = make_es256_jwt(str(uuid.uuid4()), "mgr.trigger@store.com", "manager")
    cash_token = make_es256_jwt(str(uuid.uuid4()), "cash.trigger@store.com", "cashier")

    # Manager and Cashier denied
    assert client.post("/system/sync/trigger", headers={"Authorization": f"Bearer {mgr_token}"}).status_code == 403
    assert client.post("/system/sync/trigger", headers={"Authorization": f"Bearer {cash_token}"}).status_code == 403
    assert client.post("/system/sync/trigger").status_code == 401

    # Mock sync runner to complete quickly
    set_sync_runner_override(lambda: None)

    # Owner authorized
    res_owner = client.post("/system/sync/trigger", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_owner.status_code == 202
    assert res_owner.json()["status"] == "triggered"

    # Programmer authorized
    res_prog = client.post("/system/sync/trigger", headers={"Authorization": f"Bearer {prog_token}"})
    assert res_prog.status_code == 202
    assert res_prog.json()["status"] == "triggered"

def test_system_sync_trigger_duplicate_concurrency_prevention():
    """
    Verifies that POST /system/sync/trigger prevents concurrent executions with HTTP 409 Conflict.
    """
    owner_token = make_es256_jwt(str(uuid.uuid4()), "owner.concurrent@store.com", "owner")
    import app.api.system as sys_mod

    # Simulate an active sync in progress
    with sys_mod._sync_lock:
        sys_mod._is_sync_running = True

    try:
        res = client.post("/system/sync/trigger", headers={"Authorization": f"Bearer {owner_token}"})
        assert res.status_code == 409
        assert "already in progress" in res.json()["detail"]
    finally:
        with sys_mod._sync_lock:
            sys_mod._is_sync_running = False

def test_system_sync_trigger_records_audit_event():
    """
    Verifies that POST /system/sync/trigger records the authenticated actor's UUID in technical audit logs.
    """
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.audit@store.com", "owner")

    captured_events = []
    set_audit_log_sink(lambda actor, action, resource, details: captured_events.append({
        "actor": actor,
        "action": action,
        "resource": resource,
        "details": details
    }))

    set_sync_runner_override(lambda: None)

    res = client.post("/system/sync/trigger", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 202

    sync_events = [e for e in captured_events if e["action"] == "DATA_SYNC_TRIGGERED"]
    assert len(sync_events) >= 1
    assert sync_events[0]["actor"] == owner_uid
    assert sync_events[0]["resource"] == "data/daily"

def test_system_sync_trigger_handles_background_failure_safely():
    """
    Verifies that background execution failure handles exceptions safely, releases the lock,
    and records failure status in last_sync without crashing.
    """
    owner_token = make_es256_jwt(str(uuid.uuid4()), "owner.fail@store.com", "owner")
    import app.api.system as sys_mod

    def failing_runner():
        raise RuntimeError("Simulated ingestion disk failure")

    set_sync_runner_override(failing_runner)

    res = client.post("/system/sync/trigger", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 202

    # Concurrency lock is released
    with sys_mod._sync_lock:
        assert sys_mod._is_sync_running is False

    # Status captures failure info
    res_status = client.get("/system/sync/status", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_status.status_code == 200
    assert res_status.json()["last_sync"]["status"] == "failed"

def test_system_endpoints_zero_secret_leakage():
    """
    Verifies that none of the system endpoints leak database URLs, API keys, passwords, or bearer tokens.
    """
    owner_token = make_es256_jwt(str(uuid.uuid4()), "owner.leakcheck@store.com", "owner")

    set_sync_runner_override(lambda: None)

    health_res = client.get("/system/health", headers={"Authorization": f"Bearer {owner_token}"})
    ai_res = client.get("/system/ai-status", headers={"Authorization": f"Bearer {owner_token}"})
    sync_res = client.get("/system/sync/status", headers={"Authorization": f"Bearer {owner_token}"})
    trigger_res = client.post("/system/sync/trigger", headers={"Authorization": f"Bearer {owner_token}"})

    for r in [health_res, ai_res, sync_res, trigger_res]:
        body = r.text
        assert "postgresql://" not in body
        assert "password" not in body.lower() or "password" in ["password123"] # no plain secret
        assert "sk-or-" not in body
        assert "service_role" not in body
        assert "BOOTSTRAP_SECRET" not in body

# =========================================================================
# Phase 3C: Secure Employee Account Deletion Integration Tests
# =========================================================================

def test_owner_deletes_inactive_manager():
    """1. Owner successfully deletes an inactive Manager."""
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.del1@store.com", "owner")

    target_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_id] = {
        "id": target_id,
        "full_name": "Inactive Manager",
        "email": "manager.inactive@store.com",
        "role": "manager",
        "is_active": False,
    }

    res = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["employee_id"] == target_id
    assert target_id not in TEST_EMPLOYEES

    # Verify audit log was recorded
    audit_events = [r for r in AUDIT_LOG_RECORDS if r["action_type"] == "DELETE_EMPLOYEE" and r["target_resource"] == target_id]
    assert len(audit_events) == 1
    assert audit_events[0]["performed_by"] == owner_uid

def test_owner_deletes_inactive_cashier():
    """2. Owner successfully deletes an inactive Cashier."""
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.del2@store.com", "owner")

    target_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_id] = {
        "id": target_id,
        "full_name": "Inactive Cashier",
        "email": "cashier.inactive@store.com",
        "role": "cashier",
        "is_active": False,
    }

    res = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert target_id not in TEST_EMPLOYEES

def test_owner_deletes_inactive_programmer():
    """3. Owner successfully deletes an inactive Programmer."""
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.del3@store.com", "owner")

    target_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_id] = {
        "id": target_id,
        "full_name": "Inactive Programmer",
        "email": "programmer.inactive@store.com",
        "role": "programmer",
        "is_active": False,
    }

    res = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert target_id not in TEST_EMPLOYEES

def test_active_employee_deletion_returns_409():
    """4. Active employee deletion returns HTTP 409."""
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.del4@store.com", "owner")

    target_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_id] = {
        "id": target_id,
        "full_name": "Active Employee",
        "email": "active.emp@store.com",
        "role": "cashier",
        "is_active": True,
    }

    res = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 409
    assert "deactivated" in res.json()["detail"].lower()
    # Confirm employee is NOT deleted
    assert target_id in TEST_EMPLOYEES

def test_manager_deletion_attempt_returns_403():
    """5. Manager deletion attempt returns HTTP 403."""
    mgr_uid = str(uuid.uuid4())
    mgr_token = make_es256_jwt(mgr_uid, "manager.del5@store.com", "manager")

    target_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_id] = {
        "id": target_id,
        "full_name": "Target Inactive",
        "email": "target.inactive@store.com",
        "role": "cashier",
        "is_active": False,
    }

    res = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {mgr_token}"})
    assert res.status_code == 403
    assert target_id in TEST_EMPLOYEES

def test_cashier_deletion_attempt_returns_403():
    """6. Cashier deletion attempt returns HTTP 403."""
    cashier_uid = str(uuid.uuid4())
    cashier_token = make_es256_jwt(cashier_uid, "cashier.del6@store.com", "cashier")

    target_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_id] = {
        "id": target_id,
        "full_name": "Target Inactive",
        "email": "target.inactive@store.com",
        "role": "cashier",
        "is_active": False,
    }

    res = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {cashier_token}"})
    assert res.status_code == 403
    assert target_id in TEST_EMPLOYEES

def test_programmer_deletion_attempt_returns_403():
    """7. Programmer deletion attempt returns HTTP 403."""
    prog_uid = str(uuid.uuid4())
    prog_token = make_es256_jwt(prog_uid, "prog.del7@store.com", "programmer")

    target_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_id] = {
        "id": target_id,
        "full_name": "Target Inactive",
        "email": "target.inactive@store.com",
        "role": "cashier",
        "is_active": False,
    }

    res = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {prog_token}"})
    assert res.status_code == 403
    assert target_id in TEST_EMPLOYEES

def test_nonexistent_employee_returns_404():
    """8. Nonexistent employee returns HTTP 404."""
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.del8@store.com", "owner")

    random_id = str(uuid.uuid4())
    res = client.delete(f"/employees/{random_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

def test_invalid_uuid_returns_422():
    """9. Invalid UUID returns HTTP 422."""
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.del9@store.com", "owner")

    res = client.delete("/employees/not-a-valid-uuid-12345", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 422

def test_owner_cannot_delete_own_account():
    """10. Owner cannot delete their own account."""
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.del10@store.com", "owner")

    res = client.delete(f"/employees/{owner_uid}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 400
    assert "cannot delete their own account" in res.json()["detail"].lower()
    assert owner_uid in TEST_EMPLOYEES

def test_last_active_owner_cannot_be_deleted():
    """11. Last active Owner cannot be deleted."""
    owner_a_uid = str(uuid.uuid4())
    owner_a_token = make_es256_jwt(owner_a_uid, "owner.a@store.com", "owner")

    target_owner_b_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_owner_b_id] = {
        "id": target_owner_b_id,
        "full_name": "Former Owner B",
        "email": "owner.b@store.com",
        "role": "owner",
        "is_active": False,
    }

    # Simulate that deleting owner B leaves 0 remaining active owners
    set_owner_count_fn(lambda: 0)

    res = client.delete(f"/employees/{target_owner_b_id}", headers={"Authorization": f"Bearer {owner_a_token}"})
    assert res.status_code == 400
    assert "cannot delete the last active owner" in res.json()["detail"].lower()
    assert target_owner_b_id in TEST_EMPLOYEES

def test_auth_deletion_failure_does_not_remove_profile():
    """12. Auth deletion failure does not remove the employee profile."""
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.del12@store.com", "owner")

    target_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_id] = {
        "id": target_id,
        "full_name": "Inactive Target",
        "email": "target.authfail@store.com",
        "role": "cashier",
        "is_active": False,
    }

    # Mock Auth deletion failure
    set_mock_auth_delete_fn(lambda uid: False)

    res = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 502
    assert "failed to delete employee account from supabase auth" in res.json()["detail"].lower()
    # Confirm profile was NOT deleted
    assert target_id in TEST_EMPLOYEES

def test_database_deletion_failure_after_auth_deletion_handled_safely():
    """13. Database deletion failure after Auth deletion is handled safely."""
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.del13@store.com", "owner")

    target_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_id] = {
        "id": target_id,
        "full_name": "Inactive Target",
        "email": "target.dbfail@store.com",
        "role": "cashier",
        "is_active": False,
    }

    # Auth deletion succeeds, but database deletion fails
    def fail_db_delete(emp_id, user):
        raise RuntimeError("Simulated DB connection or constraint failure")
    set_mock_delete_employee_fn(fail_db_delete)

    res = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 500
    assert "credentials were removed, but database cleanup encountered an error" in res.json()["detail"].lower()

def test_audit_logging_failure_handled_explicitly():
    """14. Audit logging failure is handled explicitly."""
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.del14@store.com", "owner")

    target_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_id] = {
        "id": target_id,
        "full_name": "Inactive Target",
        "email": "target.auditfail@store.com",
        "role": "cashier",
        "is_active": False,
    }

    # Audit logging sink raises AuditLoggingError
    def fail_audit(actor, action, target, details):
        raise AuditLoggingError("Simulated disk error on audit log table")
    set_audit_log_sink(fail_audit)

    res = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 500
    assert "audit logging failed" in res.json()["detail"].lower()

def test_historical_bills_remain_intact_after_employee_deletion():
    """15. Historical bills and business transactions remain intact."""
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.del15@store.com", "owner")

    target_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_id] = {
        "id": target_id,
        "full_name": "Inactive Cashier",
        "email": "cashier.del15@store.com",
        "role": "cashier",
        "is_active": False,
    }

    res_del = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_del.status_code == 200

    # Retrieve bills ledger to confirm business transactions are intact
    res_bills = client.get("/bills/", headers={"Authorization": f"Bearer {owner_token}"})
    assert res_bills.status_code == 200
    bills = res_bills.json()
    assert len(bills) > 0
    assert bills[0]["bill_id"] == 101

def test_repeated_deletion_requests_handled_safely():
    """16. Repeated deletion requests are handled safely."""
    owner_uid = str(uuid.uuid4())
    owner_token = make_es256_jwt(owner_uid, "owner.del16@store.com", "owner")

    target_id = str(uuid.uuid4())
    TEST_EMPLOYEES[target_id] = {
        "id": target_id,
        "full_name": "Inactive Cashier",
        "email": "cashier.repeat@store.com",
        "role": "cashier",
        "is_active": False,
    }

    # First deletion: 200 OK
    res1 = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res1.status_code == 200
    assert target_id not in TEST_EMPLOYEES

    # Second deletion attempt for same employee: 404 Not Found
    res2 = client.delete(f"/employees/{target_id}", headers={"Authorization": f"Bearer {owner_token}"})
    assert res2.status_code == 404
    assert "not found" in res2.json()["detail"].lower()





