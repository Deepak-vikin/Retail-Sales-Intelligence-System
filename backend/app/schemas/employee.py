import uuid
from typing import Optional
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
