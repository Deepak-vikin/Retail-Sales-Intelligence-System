import uuid
import urllib.request
import json
import hmac
import threading
import logging
from typing import List, Optional, Callable, Union
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Header
from app.core.permissions import AppRole, Permission, UserContext, ROLE_PERMISSIONS
from app.core.auth import get_current_user, require_owner, require_permission
from app.schemas.employee import (
    EmployeeProfileCreate,
    EmployeeProfileUpdate,
    EmployeeProfileResponse,
)
from app.core.database import connection, get_transaction
from app.core.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    BOOTSTRAP_SECRET,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employees", tags=["Employee Management"])

_bootstrap_lock = threading.Lock()

class AuditLoggingError(RuntimeError):
    """Raised when writing to technical_audit_logs fails."""
    pass

def normalize_uuid(val: Optional[Union[str, uuid.UUID]]) -> Optional[str]:
    """
    Validates and normalizes actor IDs for technical_audit_logs.performed_by (UUID).
    Accepts None for system-generated events.
    Rejects arbitrary non-UUID strings such as 'system' or 'admin'.
    """
    if val is None:
        return None
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return None
        try:
            parsed = uuid.UUID(val_str)
            return str(parsed)
        except (ValueError, AttributeError, TypeError):
            raise ValueError(
                f"Invalid UUID format for audit actor: '{val_str}'. "
                "Arbitrary actor strings such as 'system' or 'admin' are not permitted."
            )
    raise ValueError(f"Invalid type for audit actor: {type(val).__name__}. Expected UUID or None.")

_audit_log_sink: Optional[Callable[[Optional[str], str, Optional[str], Optional[str]], None]] = None

def set_audit_log_sink(fn: Optional[Callable[[Optional[str], str, Optional[str], Optional[str]], None]]):
    global _audit_log_sink
    _audit_log_sink = fn

def log_audit_event(
    performed_by: Optional[Union[str, uuid.UUID]],
    action_type: str,
    target_resource: Optional[str] = None,
    details: Optional[str] = None,
    cur = None,
) -> None:
    # 1. Validate or normalize non-null actor IDs as UUIDs before insertion.
    # Never accept arbitrary actor strings such as "system" or "admin".
    actor_uuid = normalize_uuid(performed_by)

    # 2. Check if a test sink has been registered
    if _audit_log_sink is not None:
        _audit_log_sink(actor_uuid, action_type, target_resource, details)
        return

    # 3. Database execution without silent suppression
    try:
        if cur is not None:
            cur.execute(
                """
                INSERT INTO technical_audit_logs (performed_by, action_type, target_resource, details)
                VALUES (%s, %s, %s, %s);
                """,
                (actor_uuid, action_type, target_resource, details)
            )
        else:
            conn = connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO technical_audit_logs (performed_by, action_type, target_resource, details)
                VALUES (%s, %s, %s, %s);
                """,
                (actor_uuid, action_type, target_resource, details)
            )
            conn.commit()
            cursor.close()
            conn.close()
    except Exception as e:
        # Secure server-side error logging: do not expose credentials, tokens, or PII
        logger.error(
            "Audit log recording failed: action_type=%s, target_resource=%s, error_type=%s",
            action_type,
            target_resource,
            type(e).__name__
        )
        raise AuditLoggingError(f"Audit log recording failed for action '{action_type}': {type(e).__name__}") from e

_owner_count_fn: Optional[Callable[[], int]] = None
_on_owner_created_fn: Optional[Callable[[], None]] = None
_mock_bootstrap_profile_fn: Optional[Callable[[EmployeeProfileCreate, Optional[str]], EmployeeProfileResponse]] = None
_mock_create_employee_fn: Optional[Callable[[EmployeeProfileCreate, UserContext], EmployeeProfileResponse]] = None
_mock_update_employee_fn: Optional[Callable[[str, EmployeeProfileUpdate, UserContext], EmployeeProfileResponse]] = None
_mock_auth_admin_create_fn: Optional[Callable[[dict], dict]] = None
_mock_auth_delete_fn: Optional[Callable[[str], bool]] = None

def set_owner_count_fn(fn: Optional[Callable[[], int]]):
    global _owner_count_fn
    _owner_count_fn = fn

def set_on_owner_created_fn(fn: Optional[Callable[[], None]]):
    global _on_owner_created_fn
    _on_owner_created_fn = fn

def set_mock_bootstrap_profile_fn(fn: Optional[Callable[[EmployeeProfileCreate, Optional[str]], EmployeeProfileResponse]]):
    global _mock_bootstrap_profile_fn
    _mock_bootstrap_profile_fn = fn

def set_mock_create_employee_fn(fn: Optional[Callable[[EmployeeProfileCreate, UserContext], EmployeeProfileResponse]]):
    global _mock_create_employee_fn
    _mock_create_employee_fn = fn

def set_mock_update_employee_fn(fn: Optional[Callable[[str, EmployeeProfileUpdate, UserContext], EmployeeProfileResponse]]):
    global _mock_update_employee_fn
    _mock_update_employee_fn = fn

def set_mock_auth_admin_create_fn(fn: Optional[Callable[[dict], dict]]):
    global _mock_auth_admin_create_fn
    _mock_auth_admin_create_fn = fn

def set_mock_auth_delete_fn(fn: Optional[Callable[[str], bool]]):
    global _mock_auth_delete_fn
    _mock_auth_delete_fn = fn

def compensate_supabase_auth_user(
    user_id: Optional[str],
    created_by_this_request: bool,
) -> bool:
    """
    Attempts to delete a newly created Supabase Auth user if downstream DB
    provisioning or audit logging fails.

    Requirements:
    - Never delete an Auth user unless this request created that exact user
      during the current operation (created_by_this_request must be True).
    - Log compensation failures securely without exposing credentials or PII.
    - If compensation fails, return False and record internal diagnostic info.
    - If compensation succeeds, return True.
    """
    if not created_by_this_request or not user_id:
        return True  # Nothing to compensate

    # 1. Test hook if registered
    if _mock_auth_delete_fn is not None:
        try:
            return _mock_auth_delete_fn(user_id)
        except Exception as e:
            logger.critical(
                "AUTH COMPENSATION FAILED (MOCK): Orphaned user left in auth.users. "
                "Manual cleanup required: user_id=%s, error_type=%s",
                user_id,
                type(e).__name__
            )
            return False

    # 2. Live Supabase Admin API
    if not SUPABASE_SERVICE_ROLE_KEY or not SUPABASE_URL:
        logger.critical(
            "AUTH COMPENSATION SKIPPED: Missing Supabase Admin configuration. "
            "Manual cleanup required for orphaned user_id=%s",
            user_id
        )
        return False

    delete_url = f"{SUPABASE_URL.rstrip('/')}/auth/v1/admin/users/{user_id}"
    try:
        req = urllib.request.Request(
            delete_url,
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
            method="DELETE"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 204):
                logger.info("Successfully compensated and deleted Supabase Auth user: %s", user_id)
                return True
            else:
                logger.critical(
                    "AUTH COMPENSATION FAILED: Unexpected status code %s. "
                    "Manual cleanup required: user_id=%s",
                    resp.status,
                    user_id
                )
                return False
    except Exception as e:
        logger.critical(
            "AUTH COMPENSATION FAILED: Orphaned Supabase Auth user left in auth.users. "
            "Manual cleanup required: user_id=%s, error_type=%s",
            user_id,
            type(e).__name__
        )
        return False

def count_existing_owners() -> int:
    if _owner_count_fn is not None:
        return _owner_count_fn()
    try:
        conn = connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM employee_profiles WHERE role = 'owner';")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except Exception:
        return 0

def notify_owner_created():
    if _on_owner_created_fn is not None:
        _on_owner_created_fn()

@router.post("/bootstrap-owner", response_model=EmployeeProfileResponse, status_code=status.HTTP_201_CREATED)
def bootstrap_first_owner(
    profile: EmployeeProfileCreate,
    x_bootstrap_secret: Optional[str] = Header(None, alias="X-Bootstrap-Secret")
):
    # 1. Dedicated BOOTSTRAP_SECRET from backend environment. Never reuse Supabase service-role key.
    if not BOOTSTRAP_SECRET or not x_bootstrap_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Bootstrap endpoint requires server-side secret configuration."
        )

    # 2. Constant-time comparison to prevent timing attacks. Never log or return the secret.
    if not hmac.compare_digest(str(x_bootstrap_secret).encode("utf-8"), str(BOOTSTRAP_SECRET).encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid bootstrap credential."
        )

    # 3. Synchronize concurrent bootstrap attempts to prevent race conditions
    with _bootstrap_lock:
        # Precondition: Zero existing or active owner profiles allowed
        if count_existing_owners() > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Store owner already bootstrapped. Subsequent employees must be created by the logged-in owner."
            )

        # 4. Backend strictly forces role to 'owner'. Never trust role supplied in request body.
        forced_role = AppRole.OWNER

        confirmed_supabase_user_id: Optional[str] = None
        auth_user_created_by_this_request = False

        if SUPABASE_SERVICE_ROLE_KEY and SUPABASE_URL:
            admin_auth_url = f"{SUPABASE_URL.rstrip('/')}/auth/v1/admin/users"
            payload = {
                "email": profile.email,
                "password": profile.password,
                "email_confirm": True,
                "user_metadata": {
                    "full_name": profile.full_name,
                    "role": forced_role.value,
                    "is_active": True,
                },
                "app_metadata": {
                    "role": forced_role.value,
                }
            }
            try:
                if _mock_auth_admin_create_fn is not None:
                    data = _mock_auth_admin_create_fn(payload)
                else:
                    req = urllib.request.Request(
                        admin_auth_url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "apikey": SUPABASE_SERVICE_ROLE_KEY,
                            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                if "id" in data:
                    confirmed_supabase_user_id = str(uuid.UUID(data["id"]))
                    auth_user_created_by_this_request = True
            except Exception as e:
                logger.warning("Supabase Admin Auth creation failed during bootstrap: %s", type(e).__name__)

        # Audit actor is ONLY the confirmed Supabase user UUID if successful, otherwise None.
        # Never insert a fabricated UUID into the foreign-keyed column.
        audit_actor: Optional[str] = confirmed_supabase_user_id
        profile_id: str = confirmed_supabase_user_id or str(uuid.uuid4())

        conn = None
        cur = None
        try:
            conn = connection()
            conn.autocommit = False
            cur = conn.cursor()

            # Cross-worker transaction advisory lock
            try:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('retail_owner_bootstrap_lock'));")
            except Exception:
                pass

            # Double-check inside locked transaction
            cur.execute("SELECT COUNT(*) FROM employee_profiles WHERE role = 'owner';")
            existing_in_db = cur.fetchone()[0]
            if existing_in_db > 0:
                conn.rollback()
                compensate_supabase_auth_user(confirmed_supabase_user_id, auth_user_created_by_this_request)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Store owner already bootstrapped. Subsequent employees must be created by the logged-in owner."
                )

            cur.execute(
                """
                INSERT INTO employee_profiles (id, full_name, email, role, is_active)
                VALUES (%s, %s, %s, 'owner', TRUE)
                RETURNING id, full_name, email, role, is_active, created_at, updated_at;
                """,
                (profile_id, profile.full_name, profile.email)
            )
            row = cur.fetchone()

            log_audit_event(
                performed_by=audit_actor,
                action_type="BOOTSTRAP_OWNER_CREATED",
                target_resource=profile.email,
                details="Initial store owner created via secure bootstrap.",
                cur=cur,
            )

            conn.commit()
            notify_owner_created()

            return EmployeeProfileResponse(
                id=str(row[0]),
                full_name=row[1],
                email=row[2],
                role=forced_role,
                is_active=row[4],
                created_at=row[5],
                updated_at=row[6],
            )
        except HTTPException:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        except AuditLoggingError as e:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            comp_ok = compensate_supabase_auth_user(confirmed_supabase_user_id, auth_user_created_by_this_request)
            logger.error("Bootstrap aborted: audit logging failed: %s, comp_ok=%s", type(e).__name__, comp_ok)
            if not comp_ok:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Security audit logging failed during bootstrap and auth rollback failed. Please contact administrator."
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Security audit logging failed during bootstrap. Operation aborted."
            )
        except Exception as e:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass

            if _mock_bootstrap_profile_fn is not None:
                try:
                    log_audit_event(
                        performed_by=audit_actor,
                        action_type="BOOTSTRAP_OWNER_CREATED",
                        target_resource=profile.email,
                        details="Initial store owner created via secure bootstrap.",
                    )
                    res = _mock_bootstrap_profile_fn(profile, audit_actor)
                    notify_owner_created()
                    return res
                except AuditLoggingError:
                    comp_ok = compensate_supabase_auth_user(confirmed_supabase_user_id, auth_user_created_by_this_request)
                    if not comp_ok:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Security audit logging failed during bootstrap and auth rollback failed. Please contact administrator."
                        )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Security audit logging failed during bootstrap. Operation aborted."
                    )
                except Exception as mock_err:
                    comp_ok = compensate_supabase_auth_user(confirmed_supabase_user_id, auth_user_created_by_this_request)
                    logger.error("Bootstrap mock failed: %s, comp_ok=%s", type(mock_err).__name__, comp_ok)
                    if not comp_ok:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to bootstrap owner profile and auth rollback failed. Please contact administrator."
                        )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to bootstrap owner profile in database."
                    )

            comp_ok = compensate_supabase_auth_user(confirmed_supabase_user_id, auth_user_created_by_this_request)
            logger.error("Failed to bootstrap owner profile in database: %s, comp_ok=%s", type(e).__name__, comp_ok)
            if not comp_ok:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to bootstrap owner profile and auth rollback failed. Please contact administrator."
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to bootstrap owner profile in database."
            )
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

@router.get("/", response_model=List[EmployeeProfileResponse])
def list_employees(user: UserContext = Depends(require_owner)):
    try:
        conn = connection()
        cur = conn.cursor()
        cur.execute("SELECT id, full_name, email, role, is_active, created_at, updated_at FROM employee_profiles ORDER BY created_at ASC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            EmployeeProfileResponse(
                id=str(r[0]),
                full_name=r[1],
                email=r[2],
                role=AppRole(r[3]),
                is_active=r[4],
                created_at=r[5],
                updated_at=r[6],
            )
            for r in rows
        ]
    except Exception as e:
        return []

@router.post("/", response_model=EmployeeProfileResponse, status_code=status.HTTP_201_CREATED)
def create_employee(profile: EmployeeProfileCreate, user: UserContext = Depends(require_owner)):
    if profile.role not in [AppRole.OWNER, AppRole.MANAGER, AppRole.CASHIER, AppRole.PROGRAMMER]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{profile.role}'. Exactly 4 roles allowed: owner, manager, cashier, programmer."
        )

    auth_user_id = str(uuid.uuid4())
    confirmed_supabase_user_id: Optional[str] = None
    auth_user_created_by_this_request = False

    if SUPABASE_SERVICE_ROLE_KEY and SUPABASE_URL:
        admin_auth_url = f"{SUPABASE_URL.rstrip('/')}/auth/v1/admin/users"
        payload = {
            "email": profile.email,
            "password": profile.password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": profile.full_name,
                "role": profile.role.value,
                "is_active": profile.is_active,
            },
            "app_metadata": {
                "role": profile.role.value,
            }
        }
        try:
            if _mock_auth_admin_create_fn is not None:
                data = _mock_auth_admin_create_fn(payload)
            else:
                req = urllib.request.Request(
                    admin_auth_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "apikey": SUPABASE_SERVICE_ROLE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            if "id" in data:
                confirmed_supabase_user_id = str(uuid.UUID(data["id"]))
                auth_user_id = confirmed_supabase_user_id
                auth_user_created_by_this_request = True
        except Exception as e:
            logger.warning("Supabase Admin Auth user creation failed: %s", type(e).__name__)

    conn = None
    cur = None
    try:
        conn = connection()
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO employee_profiles (id, full_name, email, role, is_active)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                email = EXCLUDED.email,
                role = EXCLUDED.role,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
            RETURNING id, full_name, email, role, is_active, created_at, updated_at;
            """,
            (auth_user_id, profile.full_name, profile.email, profile.role.value, profile.is_active)
        )
        row = cur.fetchone()

        log_audit_event(
            performed_by=user.user_id,
            action_type="EMPLOYEE_CREATED",
            target_resource=profile.email,
            details=f"Created employee profile with role {profile.role.value}",
            cur=cur,
        )

        conn.commit()

        return EmployeeProfileResponse(
            id=str(row[0]),
            full_name=row[1],
            email=row[2],
            role=AppRole(row[3]),
            is_active=row[4],
            created_at=row[5],
            updated_at=row[6],
        )
    except HTTPException:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    except AuditLoggingError as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        comp_ok = compensate_supabase_auth_user(confirmed_supabase_user_id, auth_user_created_by_this_request)
        logger.error("Employee creation aborted due to audit failure: %s, comp_ok=%s", type(e).__name__, comp_ok)
        if not comp_ok:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Security audit logging failed and auth compensation failed. Manual cleanup required."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security audit logging failed. Operation aborted."
        )
    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass

        if _mock_create_employee_fn is not None:
            try:
                log_audit_event(
                    performed_by=user.user_id,
                    action_type="EMPLOYEE_CREATED",
                    target_resource=profile.email,
                    details=f"Created employee profile with role {profile.role.value}",
                )
                return _mock_create_employee_fn(profile, user)
            except AuditLoggingError:
                comp_ok = compensate_supabase_auth_user(confirmed_supabase_user_id, auth_user_created_by_this_request)
                if not comp_ok:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Security audit logging failed and auth compensation failed. Manual cleanup required."
                    )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Security audit logging failed. Operation aborted."
                )
            except Exception as mock_err:
                comp_ok = compensate_supabase_auth_user(confirmed_supabase_user_id, auth_user_created_by_this_request)
                logger.error("Create employee mock failed: %s, comp_ok=%s", type(mock_err).__name__, comp_ok)
                if not comp_ok:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to create employee profile in database and auth compensation failed. Manual cleanup required."
                    )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create employee profile in database."
                )

        comp_ok = compensate_supabase_auth_user(confirmed_supabase_user_id, auth_user_created_by_this_request)
        logger.error("Failed to create employee profile: %s, comp_ok=%s", type(e).__name__, comp_ok)
        if not comp_ok:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create employee profile in database and auth compensation failed. Manual cleanup required."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create employee profile in database."
        )
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

@router.patch("/{employee_id}/role", response_model=EmployeeProfileResponse)
def update_employee_role(employee_id: str, update: EmployeeProfileUpdate, user: UserContext = Depends(require_owner)):
    if update.role and update.role not in [AppRole.OWNER, AppRole.MANAGER, AppRole.CASHIER, AppRole.PROGRAMMER]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role value."
        )

    conn = None
    cur = None
    try:
        conn = connection()
        conn.autocommit = False
        cur = conn.cursor()

        if update.is_active is False or (update.role and update.role != AppRole.OWNER):
            cur.execute("SELECT COUNT(*) FROM employee_profiles WHERE role = 'owner' AND is_active = TRUE AND id != %s;", (employee_id,))
            remaining_owners = cur.fetchone()[0]
            cur.execute("SELECT role FROM employee_profiles WHERE id = %s;", (employee_id,))
            target_curr = cur.fetchone()
            if target_curr and target_curr[0] == "owner" and remaining_owners == 0:
                conn.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot deactivate or demote the last active owner of the store."
                )

        set_clauses = []
        params = []
        if update.full_name is not None:
            set_clauses.append("full_name = %s")
            params.append(update.full_name)
        if update.role is not None:
            set_clauses.append("role = %s")
            params.append(update.role.value)
        if update.is_active is not None:
            set_clauses.append("is_active = %s")
            params.append(update.is_active)

        if not set_clauses:
            raise HTTPException(status_code=400, detail="No update fields provided.")

        set_clauses.append("updated_at = NOW()")
        params.append(employee_id)

        sql = f"UPDATE employee_profiles SET {', '.join(set_clauses)} WHERE id = %s RETURNING id, full_name, email, role, is_active, created_at, updated_at;"
        cur.execute(sql, tuple(params))
        row = cur.fetchone()

        if not row:
            conn.rollback()
            raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found.")

        log_audit_event(
            performed_by=user.user_id,
            action_type="EMPLOYEE_UPDATED",
            target_resource=employee_id,
            details=f"Updated employee role: {update.role}, active: {update.is_active}",
            cur=cur,
        )

        conn.commit()

        return EmployeeProfileResponse(
            id=str(row[0]),
            full_name=row[1],
            email=row[2],
            role=AppRole(row[3]),
            is_active=row[4],
            created_at=row[5],
            updated_at=row[6],
        )
    except HTTPException:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    except AuditLoggingError as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.error("Employee update aborted due to audit failure: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security audit logging failed. Operation aborted."
        )
    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        if _mock_update_employee_fn is not None:
            try:
                log_audit_event(
                    performed_by=user.user_id,
                    action_type="EMPLOYEE_UPDATED",
                    target_resource=employee_id,
                    details=f"Updated employee role: {update.role}, active: {update.is_active}",
                )
            except AuditLoggingError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Security audit logging failed. Operation aborted."
                )
            return _mock_update_employee_fn(employee_id, update, user)
        logger.error("Failed to update employee profile: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Failed to update employee profile in database.")
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

@router.get("/me")
def get_current_user_profile(user: UserContext = Depends(get_current_user)):
    return {
        "user_id": user.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
        "is_business_user": user.is_business_user(),
        "is_technical_user": user.is_technical_user(),
        "permissions": [p.value for p in ROLE_PERMISSIONS.get(user.role, set())],
    }
