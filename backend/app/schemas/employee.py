import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.core.permissions import AppRole

class EmployeeProfileBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: Optional[str] = None
    role: AppRole
    is_active: bool = True

class EmployeeProfileCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=100)
    full_name: str = Field(min_length=1, max_length=100)
    role: AppRole
    is_active: bool = True

class EmployeeProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[AppRole] = None
    is_active: Optional[bool] = None

class EmployeeProfileResponse(EmployeeProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class EmployeeDeleteResponse(BaseModel):
    status: str = "success"
    message: str
    employee_id: str

class SystemHealthResponse(BaseModel):
    status: str
    database_connected: bool
    llm_gateway_configured: bool
    supabase_auth_configured: bool
    roles_supported: list[str]
    timestamp: datetime

class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    log_id: int
    performed_by: Optional[str] = None
    action_type: str
    target_resource: Optional[str] = None
    details: Optional[str] = None
    performed_at: Optional[datetime] = None

class AIGatewayStatusResponse(BaseModel):
    provider: str
    is_configured: bool
    provider_reachable: Optional[bool] = None
    primary_model: str
    fallback_models: List[str]
    all_models: List[str]
    fallback_count: int
    status: str

class DataSyncQueueMetrics(BaseModel):
    pending_sales: int
    pending_purchases: int
    processed_sales: int
    processed_purchases: int
    rejected_sales: int
    rejected_purchases: int
    total_pending: int
    total_processed: int
    total_rejected: int

class DataSyncStatusResponse(BaseModel):
    status: str
    is_syncing: bool
    queue: DataSyncQueueMetrics
    last_sync: Optional[Dict[str, Any]] = None
    scheduler_configured: bool
    timestamp: datetime

class DataSyncTriggerResponse(BaseModel):
    status: str
    message: str
    triggered_by: Optional[str] = None
    started_at: datetime
