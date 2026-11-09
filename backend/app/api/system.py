import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from fastapi import APIRouter, Depends
from app.core.permissions import AppRole, Permission, UserContext
from app.core.auth import get_current_user, require_permission, require_role
from app.core.database import connection
from app.core.config import OPENROUTER_API_KEY, SUPABASE_URL, SUPABASE_JWKS_URL
from app.schemas.employee import SystemHealthResponse, AuditLogResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["System Maintenance & Health"])

_audit_logs_reader: Optional[Callable[[int], List[Dict[str, Any]]]] = None

def set_audit_logs_reader(fn: Optional[Callable[[int], List[Dict[str, Any]]]]):
    global _audit_logs_reader
    _audit_logs_reader = fn

@router.get("/health", response_model=SystemHealthResponse)
def system_health(user: UserContext = Depends(require_permission(Permission.SYSTEM_HEALTH_MONITOR))):
    db_ok = False
    try:
        conn = connection()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        db_ok = cur.fetchone()[0] == 1
        cur.close()
        conn.close()
    except Exception:
        db_ok = False

    return SystemHealthResponse(
        status="healthy" if db_ok else "degraded",
        database_connected=db_ok,
        llm_gateway_configured=bool(OPENROUTER_API_KEY),
        supabase_auth_configured=bool(SUPABASE_URL and SUPABASE_JWKS_URL),
        roles_supported=["owner", "manager", "cashier", "programmer"],
        timestamp=datetime.now(),
    )

@router.get("/audit-logs", response_model=List[AuditLogResponse])
def view_audit_logs(
    limit: int = 50,
    user: UserContext = Depends(require_role(AppRole.OWNER, AppRole.PROGRAMMER))
):
    if _audit_logs_reader is not None:
        return _audit_logs_reader(limit)

    try:
        conn = connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT log_id, performed_by, action_type, target_resource, details, performed_at
            FROM technical_audit_logs
            ORDER BY performed_at DESC
            LIMIT %s;
            """,
            (limit,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "log_id": r[0],
                "performed_by": str(r[1]) if r[1] is not None else None,
                "action_type": r[2],
                "target_resource": r[3],
                "details": r[4],
                "performed_at": r[5],
            }
            for r in rows
        ]
    except Exception as e:
        # Secure server-side error logging: never expose credentials or internal DB details to clients
        logger.error("Failed to retrieve technical audit logs: %s", type(e).__name__)
        return []
