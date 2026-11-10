import os
import re
import logging
import threading
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Query

from app.core.permissions import AppRole, Permission, UserContext
from app.core.auth import get_current_user, require_permission, require_role
from app.core.database import connection
from app.core.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    PRIMARY_MODEL,
    FALLBACK_MODEL,
    SUPABASE_URL,
    SUPABASE_JWKS_URL,
    ROOT_DIR,
)
from app.schemas.employee import (
    SystemHealthResponse,
    AuditLogResponse,
    AIGatewayStatusResponse,
    DataSyncStatusResponse,
    DataSyncTriggerResponse,
    DataSyncQueueMetrics,
)
from app.api.employees import log_audit_event, AuditLoggingError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["System Maintenance & Health"])

_audit_logs_reader: Optional[Callable[[int], List[Dict[str, Any]]]] = None
_ai_connectivity_check_fn: Optional[Callable[[], bool]] = None
_sync_runner_override: Optional[Callable[[], None]] = None

_sync_lock = threading.Lock()
_is_sync_running = False
_last_sync_info: Dict[str, Any] = {
    "status": "idle",
    "started_at": None,
    "completed_at": None,
    "error": None,
}

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_JWT_PATTERN = re.compile(r"\bey[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_TOKEN_PATTERN = re.compile(r"(?i)\b(?:bearer|token|key|secret)\s+['\"]?[A-Za-z0-9-._~+/=]{8,}['\"]?")

def _redact_pii_string(val: Optional[str]) -> Optional[str]:
    if not val:
        return val
    text = str(val)
    text = _JWT_PATTERN.sub("[REDACTED_JWT]", text)
    text = _TOKEN_PATTERN.sub("[REDACTED_TOKEN]", text)
    text = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    return text

def _sanitize_log_record_for_programmer(record: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(record)
    if cleaned.get("target_resource"):
        cleaned["target_resource"] = _redact_pii_string(cleaned["target_resource"])
    if cleaned.get("details"):
        cleaned["details"] = _redact_pii_string(cleaned["details"])
    return cleaned

def set_audit_logs_reader(fn: Optional[Callable[[int], List[Dict[str, Any]]]]):
    global _audit_logs_reader
    _audit_logs_reader = fn

def set_ai_connectivity_check_fn(fn: Optional[Callable[[], bool]]):
    global _ai_connectivity_check_fn
    _ai_connectivity_check_fn = fn

def set_sync_runner_override(fn: Optional[Callable[[], None]]):
    global _sync_runner_override
    _sync_runner_override = fn

def _get_base_data_path() -> Path:
    p = Path("data")
    if p.is_dir():
        return p
    if ROOT_DIR and (ROOT_DIR / "data").is_dir():
        return ROOT_DIR / "data"
    return p

def _count_csv_files(folder_path: Path) -> int:
    try:
        if not folder_path.is_dir():
            return 0
        return sum(1 for f in folder_path.iterdir() if f.is_file() and f.suffix.lower() == ".csv")
    except Exception:
        return 0

def _get_model_hierarchy() -> List[str]:
    primary = os.getenv("PRIMARY_MODEL", PRIMARY_MODEL or "nvidia/nemotron-3-nano-30b-a3b:free")
    fb1 = os.getenv("FALLBACK_MODEL", FALLBACK_MODEL or "meta-llama/llama-3.3-70b-instruct:free")
    fb2 = os.getenv("FALLBACK_MODEL_2", "google/gemma-4-31b-it:free")
    fb3 = os.getenv("FALLBACK_MODEL_3", "nvidia/nemotron-3.5-lightning:free")
    return list(dict.fromkeys([primary, fb1, fb2, fb3]))

def _check_ai_connectivity() -> Optional[bool]:
    if _ai_connectivity_check_fn is not None:
        return _ai_connectivity_check_fn()
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.strip():
        return False
    try:
        base = OPENROUTER_BASE_URL.rstrip('/') if OPENROUTER_BASE_URL else "https://openrouter.ai/api/v1"
        req = urllib.request.Request(
            f"{base}/models",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "User-Agent": "RetailSalesPlatform/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except Exception:
        return False

def _execute_sync_task(actor_id: Optional[str]):
    global _is_sync_running, _last_sync_info
    try:
        if _sync_runner_override is not None:
            _sync_runner_override()
        else:
            from app.jobs.daily_sync_job import run_daily_sync
            run_daily_sync()
        _last_sync_info["status"] = "success"
        _last_sync_info["completed_at"] = datetime.now()
        _last_sync_info["error"] = None
    except Exception as e:
        logger.error("Background data sync failed: %s", type(e).__name__)
        _last_sync_info["status"] = "failed"
        _last_sync_info["completed_at"] = datetime.now()
        _last_sync_info["error"] = str(type(e).__name__)
    finally:
        with _sync_lock:
            _is_sync_running = False

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
        llm_gateway_configured=bool(OPENROUTER_API_KEY and OPENROUTER_API_KEY.strip()),
        supabase_auth_configured=bool(SUPABASE_URL and SUPABASE_JWKS_URL),
        roles_supported=["owner", "manager", "cashier", "programmer"],
        timestamp=datetime.now(),
    )

@router.get("/ai-status", response_model=AIGatewayStatusResponse)
def ai_gateway_status(
    check_connectivity: bool = False,
    user: UserContext = Depends(require_permission(Permission.SYSTEM_HEALTH_MONITOR))
):
    """
    Returns AI Gateway configuration, model failover hierarchy, and optional connectivity status.
    Never exposes API keys or secrets.
    """
    is_configured = bool(OPENROUTER_API_KEY and OPENROUTER_API_KEY.strip())
    hierarchy = _get_model_hierarchy()
    primary = hierarchy[0] if hierarchy else "unknown"
    fallbacks = hierarchy[1:] if len(hierarchy) > 1 else []

    reachable = None
    if check_connectivity:
        reachable = _check_ai_connectivity()

    if not is_configured:
        status_str = "unconfigured"
    elif reachable is False:
        status_str = "unreachable"
    elif reachable is True:
        status_str = "operational"
    else:
        status_str = "configured"

    return AIGatewayStatusResponse(
        provider="OpenRouter",
        is_configured=is_configured,
        provider_reachable=reachable,
        primary_model=primary,
        fallback_models=fallbacks,
        all_models=hierarchy,
        fallback_count=len(fallbacks),
        status=status_str,
    )

@router.get("/sync/status", response_model=DataSyncStatusResponse)
def data_sync_status(
    user: UserContext = Depends(require_permission(Permission.SYSTEM_HEALTH_MONITOR))
):
    """
    Returns CSV file counts across pending, processed, and rejected queues.
    Handles missing directories safely and never exposes sensitive filesystem paths.
    """
    base_dir = _get_base_data_path()
    pending_sales = _count_csv_files(base_dir / "daily" / "sales")
    pending_purchases = _count_csv_files(base_dir / "daily" / "purchases")
    processed_sales = _count_csv_files(base_dir / "processed" / "sales")
    processed_purchases = _count_csv_files(base_dir / "processed" / "purchases")
    rejected_sales = _count_csv_files(base_dir / "rejected" / "sales")
    rejected_purchases = _count_csv_files(base_dir / "rejected" / "purchases")

    queue = DataSyncQueueMetrics(
        pending_sales=pending_sales,
        pending_purchases=pending_purchases,
        processed_sales=processed_sales,
        processed_purchases=processed_purchases,
        rejected_sales=rejected_sales,
        rejected_purchases=rejected_purchases,
        total_pending=pending_sales + pending_purchases,
        total_processed=processed_sales + processed_purchases,
        total_rejected=rejected_sales + rejected_purchases,
    )

    with _sync_lock:
        currently_syncing = _is_sync_running

    status_str = "in_progress" if currently_syncing else ("degraded" if (queue.rejected_sales + queue.rejected_purchases) > 0 else "idle")

    return DataSyncStatusResponse(
        status=status_str,
        is_syncing=currently_syncing,
        queue=queue,
        last_sync=_last_sync_info if _last_sync_info.get("started_at") else None,
        scheduler_configured=True,
        timestamp=datetime.now(),
    )

@router.post("/sync/trigger", response_model=DataSyncTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_data_sync(
    background_tasks: BackgroundTasks,
    user: UserContext = Depends(require_role(AppRole.OWNER, AppRole.PROGRAMMER))
):
    """
    Dispatches run_daily_sync() asynchronously in the background.
    Prevents concurrent executions, records audit telemetry, and returns immediate status.
    """
    global _is_sync_running, _last_sync_info

    with _sync_lock:
        if _is_sync_running:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A data synchronization job is already in progress."
            )
        _is_sync_running = True

    now = datetime.now()
    _last_sync_info = {
        "status": "in_progress",
        "started_at": now,
        "completed_at": None,
        "error": None,
    }

    # Record technical audit event for manual synchronization trigger
    try:
        log_audit_event(
            performed_by=user.user_id,
            action_type="DATA_SYNC_TRIGGERED",
            target_resource="data/daily",
            details="Manual CSV synchronization job triggered via System Maintenance API.",
        )
    except Exception as e:
        logger.warning("Audit event recording for sync trigger failed: %s", type(e).__name__)

    background_tasks.add_task(_execute_sync_task, user.user_id)

    return DataSyncTriggerResponse(
        status="triggered",
        message="Data synchronization job dispatched in the background.",
        triggered_by=user.user_id,
        started_at=now,
    )

@router.get("/audit-logs", response_model=List[AuditLogResponse])
def view_audit_logs(
    limit: int = 50,
    user: UserContext = Depends(require_role(AppRole.OWNER, AppRole.PROGRAMMER))
):
    raw_logs = []
    if _audit_logs_reader is not None:
        fetched = _audit_logs_reader(limit)
        for r in fetched:
            if isinstance(r, dict):
                raw_logs.append(dict(r))
            elif hasattr(r, "model_dump"):
                raw_logs.append(r.model_dump())
            else:
                raw_logs.append({
                    "log_id": getattr(r, "log_id", None),
                    "performed_by": getattr(r, "performed_by", None),
                    "action_type": getattr(r, "action_type", None),
                    "target_resource": getattr(r, "target_resource", None),
                    "details": getattr(r, "details", None),
                    "performed_at": getattr(r, "performed_at", None),
                })
    else:
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
            raw_logs = [
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

    if user.role == AppRole.PROGRAMMER:
        return [_sanitize_log_record_for_programmer(r) for r in raw_logs]
    return raw_logs
