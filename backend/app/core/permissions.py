from enum import Enum
from typing import Set, Dict, Optional
from pydantic import BaseModel, Field

class AppRole(str, Enum):
    OWNER = "owner"
    MANAGER = "manager"
    CASHIER = "cashier"
    PROGRAMMER = "programmer"

class Permission(str, Enum):
    BILLING_CREATE = "billing:create"
    BILLING_READ = "billing:read"
    BILLING_MANAGE = "billing:manage"

    PRODUCTS_READ = "products:read"
    PRODUCTS_MANAGE = "products:manage"

    INVENTORY_READ = "inventory:read"
    INVENTORY_MANAGE = "inventory:manage"

    SUPPLIERS_READ = "suppliers:read"
    SUPPLIERS_MANAGE = "suppliers:manage"

    PURCHASES_READ = "purchases:read"
    PURCHASES_MANAGE = "purchases:manage"

    ANALYTICS_READ = "analytics:read"
    AI_QUERY_BUSINESS = "ai_query:business"

    EMPLOYEES_MANAGE = "employees:manage"
    BUSINESS_SETTINGS = "business:settings"
    AUDIT_LOGS_VIEW = "audit_logs:view"

    SYSTEM_HEALTH_MONITOR = "system:health_monitor"
    APPLICATION_LOGS_VIEW = "system:logs_view"
    AI_CONFIG_MANAGE = "system:ai_config"
    INGESTION_MANAGE = "system:ingestion_manage"
    TECHNICAL_MAINTENANCE = "system:technical_maintenance"

BUSINESS_ROLES: Set[AppRole] = {
    AppRole.OWNER,
    AppRole.MANAGER,
    AppRole.CASHIER,
}

TECHNICAL_ROLES: Set[AppRole] = {
    AppRole.PROGRAMMER,
}

ROLE_PERMISSIONS: Dict[AppRole, Set[Permission]] = {
    AppRole.OWNER: {
        Permission.BILLING_CREATE,
        Permission.BILLING_READ,
        Permission.BILLING_MANAGE,
        Permission.PRODUCTS_READ,
        Permission.PRODUCTS_MANAGE,
        Permission.INVENTORY_READ,
        Permission.INVENTORY_MANAGE,
        Permission.SUPPLIERS_READ,
        Permission.SUPPLIERS_MANAGE,
        Permission.PURCHASES_READ,
        Permission.PURCHASES_MANAGE,
        Permission.ANALYTICS_READ,
        Permission.AI_QUERY_BUSINESS,
        Permission.EMPLOYEES_MANAGE,
        Permission.BUSINESS_SETTINGS,
        Permission.AUDIT_LOGS_VIEW,
        Permission.SYSTEM_HEALTH_MONITOR,
    },
    AppRole.MANAGER: {
        Permission.BILLING_CREATE,
        Permission.BILLING_READ,
        Permission.BILLING_MANAGE,
        Permission.PRODUCTS_READ,
        Permission.PRODUCTS_MANAGE,
        Permission.INVENTORY_READ,
        Permission.INVENTORY_MANAGE,
        Permission.SUPPLIERS_READ,
        Permission.SUPPLIERS_MANAGE,
        Permission.PURCHASES_READ,
        Permission.PURCHASES_MANAGE,
        Permission.ANALYTICS_READ,
        Permission.AI_QUERY_BUSINESS,
    },
    AppRole.CASHIER: {
        Permission.BILLING_CREATE,
        Permission.BILLING_READ,
        Permission.PRODUCTS_READ,
        Permission.INVENTORY_READ,
    },
    AppRole.PROGRAMMER: {
        Permission.SYSTEM_HEALTH_MONITOR,
        Permission.APPLICATION_LOGS_VIEW,
        Permission.AI_CONFIG_MANAGE,
        Permission.INGESTION_MANAGE,
        Permission.TECHNICAL_MAINTENANCE,
    },
}

class UserContext(BaseModel):
    user_id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: AppRole
    is_active: bool = True

    def has_permission(self, permission: Permission) -> bool:
        if not self.is_active:
            return False
        return permission in ROLE_PERMISSIONS.get(self.role, set())

    def can_manage_role(self, target_role: AppRole) -> bool:
        if self.role != AppRole.OWNER:
            return False
        return True

    def is_business_user(self) -> bool:
        return self.role in BUSINESS_ROLES

    def is_technical_user(self) -> bool:
        return self.role in TECHNICAL_ROLES
