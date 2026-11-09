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
    compensate_supabase_auth_user,
    EmployeeProfileResponse,
)
from app.api.system import set_audit_logs_reader
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
    monkeypatch.setattr("app.api.employees.BOOTSTRAP_SECRET", BOOTSTRAP_TEST_SECRET)
    monkeypatch.setattr("app.api.employees.SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key-999")

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

def test_bootstrap_with_successful_supabase_auth_creation(monkeypatch):
    confirmed_id = "6d78198a-7ebc-4949-b6f4-b0f1e1294b29"

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
    bootstrap_audit = [r for r in AUDIT_LOG_RECORDS if r["action_type"] == "BOOTSTRAP_OWNER_CREATED"][-1]
    # Must use the confirmed Supabase user UUID
    assert bootstrap_audit["performed_by"] == confirmed_id

def test_bootstrap_when_supabase_auth_creation_fails(monkeypatch):
    def mock_urlopen_fail(req, timeout=10):
        raise urllib.error.URLError("Network unreachable")

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen_fail)
    set_owner_count_fn(lambda: 0)

    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "unconfirmed@test.com", "password": "Password123!", "full_name": "Unconfirmed Owner", "role": "owner"}
    )
    assert res.status_code == 201
    bootstrap_audit = [r for r in AUDIT_LOG_RECORDS if r["action_type"] == "BOOTSTRAP_OWNER_CREATED"][-1]
    # When Supabase creation fails, audit actor MUST be None (never a fabricated UUID)
    assert bootstrap_audit["performed_by"] is None

def test_bootstrap_never_inserts_fabricated_uuid(monkeypatch):
    def mock_urlopen_fail(req, timeout=10):
        raise urllib.error.URLError("Network down")

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen_fail)
    set_owner_count_fn(lambda: 0)

    res = client.post(
        "/employees/bootstrap-owner",
        headers={"X-Bootstrap-Secret": BOOTSTRAP_TEST_SECRET},
        json={"email": "nofabricated@test.com", "password": "Password123!", "full_name": "No Fabricated UUID", "role": "owner"}
    )
    assert res.status_code == 201
    created_profile_id = res.json()["id"]

    bootstrap_audit = [r for r in AUDIT_LOG_RECORDS if r["action_type"] == "BOOTSTRAP_OWNER_CREATED"][-1]
    # The profile ID might be locally created for mock response, but performed_by MUST NOT be that local UUID
    assert bootstrap_audit["performed_by"] != created_profile_id
    assert bootstrap_audit["performed_by"] is None

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
    assert create_audits[-1]["target_resource"] == "staff1@test.com"

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


