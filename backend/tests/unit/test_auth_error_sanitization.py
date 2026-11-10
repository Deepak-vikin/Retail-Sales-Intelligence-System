import io
import json
import logging
import urllib.error
import pytest
from starlette.testclient import TestClient
from app.main import app
from app.api.employees import (
    _sanitize_auth_error_body,
    set_mock_auth_admin_create_fn,
    BOOTSTRAP_SECRET,
)
from app.core.auth import get_current_user
from app.core.permissions import AppRole, UserContext, ROLE_PERMISSIONS

client = TestClient(app)

def make_http_error(code: int, body_str: str, url: str = "https://example.supabase.co/auth/v1/admin/users") -> urllib.error.HTTPError:
    fp = io.BytesIO(body_str.encode("utf-8"))
    return urllib.error.HTTPError(
        url=url,
        code=code,
        msg=f"HTTP {code}",
        hdrs={},
        fp=fp,
    )

# ---------------------------------------------------------------------------
# Unit tests: _sanitize_auth_error_body
# ---------------------------------------------------------------------------

def test_sanitize_empty_and_whitespace():
    assert _sanitize_auth_error_body("") == "<empty response>"
    assert _sanitize_auth_error_body(None) == "<empty response>"
    assert _sanitize_auth_error_body("   \n\t  ") == "<empty response>"

def test_sanitize_redacts_jwt_tokens():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    raw = f"Error: Token validation failed for token {jwt}"
    sanitized = _sanitize_auth_error_body(raw)
    assert jwt not in sanitized
    assert "[REDACTED_JWT]" in sanitized

def test_sanitize_redacts_supabase_keys():
    sb_secret = "sb_secret_test_placeholder"
    sb_anon = "sb_anon_xyz1234567890abcdef"
    sbp_key = "sbp_abcdef0123456789"
    raw = f"Invalid API keys passed: {sb_secret}, {sb_anon}, and {sbp_key}"
    sanitized = _sanitize_auth_error_body(raw)
    assert sb_secret not in sanitized
    assert sb_anon not in sanitized
    assert sbp_key not in sanitized
    assert "[REDACTED_KEY]" in sanitized

def test_sanitize_redacts_email_addresses():
    raw = "User registration failed for admin@store.com and employee.one+tag@sub.example.co.uk"
    sanitized = _sanitize_auth_error_body(raw)
    assert "admin@store.com" not in sanitized
    assert "employee.one+tag@sub.example.co.uk" not in sanitized
    assert "[REDACTED_EMAIL]" in sanitized

def test_sanitize_redacts_bearer_tokens():
    raw = "Failed request with header Bearer eyJhbGciOiJIUzI1NiJ9.abc.def and bearer secret_admin_token_xyz"
    sanitized = _sanitize_auth_error_body(raw)
    assert "secret_admin_token_xyz" not in sanitized
    assert "Bearer [REDACTED_TOKEN]" in sanitized

def test_sanitize_redacts_unquoted_and_quoted_passwords_and_secrets():
    raw = "Authentication rejected: password=MySecretPassword123, secret: 'top_secret_val', apikey: 998877"
    sanitized = _sanitize_auth_error_body(raw)
    assert "MySecretPassword123" not in sanitized
    assert "top_secret_val" not in sanitized
    assert "998877" not in sanitized
    assert '[REDACTED]' in sanitized

def test_sanitize_nested_json_structures():
    data = {
        "error": "Bad request",
        "code": 400,
        "details": {
            "password": "supersecretpassword123",
            "api_key": "sb_secret_something_special",
            "user_metadata": {
                "full_name": "Alice Doe",
                "email": "alice@example.com"
            },
            "credentials": [
                {"token": "token123"},
                {"refresh_token": "refresh456"}
            ],
            "items": [
                {"token": "token123"},
                {"safe_item": "hello"}
            ],
            "safe_code": "ERR_VALIDATION_01"
        }
    }
    raw = json.dumps(data)
    sanitized = _sanitize_auth_error_body(raw)
    parsed = json.loads(sanitized)
    
    # Sensitive nested fields must be replaced with [REDACTED]
    assert parsed["details"]["password"] == "[REDACTED]"
    assert parsed["details"]["api_key"] == "[REDACTED]"
    assert parsed["details"]["user_metadata"] == "[REDACTED]"
    assert parsed["details"]["credentials"] == "[REDACTED]"
    assert parsed["details"]["items"][0]["token"] == "[REDACTED]"
    assert parsed["details"]["items"][1]["safe_item"] == "hello"
    
    # Non-sensitive structure preserved
    assert parsed["code"] == 400
    assert parsed["details"]["safe_code"] == "ERR_VALIDATION_01"
    assert "supersecretpassword123" not in sanitized
    assert "alice@example.com" not in sanitized

def test_sanitize_truncation():
    long_body = "x" * 2500
    sanitized = _sanitize_auth_error_body(long_body, max_len=1000)
    assert len(sanitized) == 1000 + len("... [TRUNCATED]")
    assert sanitized.endswith("... [TRUNCATED]")

# ---------------------------------------------------------------------------
# Integration tests: HTTP status capture and diagnostic logging
# ---------------------------------------------------------------------------

def test_bootstrap_captures_http_status_and_sanitizes_body_in_logs(caplog, monkeypatch):
    """
    Verifies that when Supabase Admin Auth fails during bootstrap with HTTPError:
    1. HTTP status code is captured in logs.
    2. Response body is sanitized before logging (no secret leakage).
    3. HTTP 502 response contract is preserved.
    """
    secret_body = json.dumps({
        "message": "Auth failure",
        "password": "UnsafePasswordToLeak",
        "email": "bootstrap_owner@store.com",
        "code": "auth_error"
    })
    
    def raise_http_error(_payload):
        raise make_http_error(404, secret_body)

    set_mock_auth_admin_create_fn(raise_http_error)
    try:
        # Guarantee BOOTSTRAP_SECRET and zero owners
        test_secret = "test-bootstrap-secret-sanitization"
        monkeypatch.setattr("app.api.employees.BOOTSTRAP_SECRET", test_secret)
        monkeypatch.setattr("app.api.employees.count_existing_owners", lambda: 0)

        with caplog.at_level(logging.ERROR):
            resp = client.post(
                "/employees/bootstrap-owner",
                headers={"X-Bootstrap-Secret": test_secret},
                json={
                    "email": "owner@store.com",
                    "password": "TestPassword123!",
                    "full_name": "Test Owner",
                    "role": "owner"
                }
            )

        assert resp.status_code == 502
        assert resp.json()["detail"] == "Failed to create owner identity in Supabase Auth: HTTPError."

        # Verify logs captured status code 404 and sanitized body
        matching_logs = [record for record in caplog.records if "Supabase Admin Auth creation failed during bootstrap" in record.message]
        assert len(matching_logs) >= 1
        log_message = matching_logs[0].message
        assert "HTTP 404" in log_message
        assert "UnsafePasswordToLeak" not in log_message
        assert "bootstrap_owner@store.com" not in log_message
        assert "[REDACTED]" in log_message
    finally:
        set_mock_auth_admin_create_fn(None)

def test_create_employee_captures_http_status_and_sanitizes_body_in_logs(caplog):
    """
    Verifies that when Supabase Admin Auth fails during create_employee with HTTPError:
    1. HTTP status code is captured in logs.
    2. Response body is sanitized before logging.
    3. HTTP 502 response contract is preserved.
    """
    secret_body = "Error 422: password=EmployeeSecretPass and email=employee@store.com invalid"
    
    def raise_http_error(_payload):
        raise make_http_error(422, secret_body)

    set_mock_auth_admin_create_fn(raise_http_error)
    try:
        # Override auth dependency to simulate authenticated owner
        app.dependency_overrides[get_current_user] = lambda: UserContext(
            user_id="11111111-1111-1111-1111-111111111111",
            role=AppRole.OWNER,
            permissions=ROLE_PERMISSIONS[AppRole.OWNER],
        )

        with caplog.at_level(logging.ERROR):
            resp = client.post(
                "/employees/",
                json={
                    "email": "new.employee@store.com",
                    "password": "ValidPassword123!",
                    "full_name": "New Employee",
                    "role": "cashier",
                    "is_active": True
                }
            )

        assert resp.status_code == 502
        assert resp.json()["detail"] == "Failed to create employee identity in Supabase Auth: HTTPError."

        matching_logs = [record for record in caplog.records if "Supabase Admin Auth user creation failed" in record.message]
        assert len(matching_logs) >= 1
        log_message = matching_logs[0].message
        assert "HTTP 422" in log_message
        assert "EmployeeSecretPass" not in log_message
        assert "employee@store.com" not in log_message
        assert "[REDACTED]" in log_message or "[REDACTED_EMAIL]" in log_message
    finally:
        set_mock_auth_admin_create_fn(None)
        app.dependency_overrides.pop(get_current_user, None)

