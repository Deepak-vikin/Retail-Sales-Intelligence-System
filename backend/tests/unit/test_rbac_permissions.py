import pytest
from app.core.permissions import (
    AppRole,
    Permission,
    UserContext,
    ROLE_PERMISSIONS,
    BUSINESS_ROLES,
    TECHNICAL_ROLES,
)

def test_four_roles_exact_values():
    assert len(AppRole) == 4
    roles = {r.value for r in AppRole}
    assert roles == {"owner", "manager", "cashier", "programmer"}

def test_separation_of_business_and_technical_roles():
    assert AppRole.OWNER in BUSINESS_ROLES
    assert AppRole.MANAGER in BUSINESS_ROLES
    assert AppRole.CASHIER in BUSINESS_ROLES
    assert AppRole.PROGRAMMER in TECHNICAL_ROLES

    assert BUSINESS_ROLES.isdisjoint(TECHNICAL_ROLES)

def test_programmer_has_no_business_financial_or_billing_access():
    programmer = UserContext(user_id="p1", username="dev", role=AppRole.PROGRAMMER)

    assert not programmer.has_permission(Permission.BILLING_READ)
    assert not programmer.has_permission(Permission.BILLING_CREATE)
    assert not programmer.has_permission(Permission.BILLING_MANAGE)
    assert not programmer.has_permission(Permission.ANALYTICS_READ)
    assert not programmer.has_permission(Permission.AI_QUERY_BUSINESS)
    assert not programmer.has_permission(Permission.EMPLOYEES_MANAGE)
    assert not programmer.has_permission(Permission.PURCHASES_READ)
    assert not programmer.has_permission(Permission.SUPPLIERS_READ)

    assert programmer.has_permission(Permission.SYSTEM_HEALTH_MONITOR)
    assert programmer.has_permission(Permission.APPLICATION_LOGS_VIEW)
    assert programmer.has_permission(Permission.AI_CONFIG_MANAGE)
    assert programmer.has_permission(Permission.TECHNICAL_MAINTENANCE)

def test_programmer_cannot_assign_roles_or_promote_self():
    programmer = UserContext(user_id="p1", username="dev", role=AppRole.PROGRAMMER)
    assert not programmer.can_manage_role(AppRole.OWNER)
    assert not programmer.can_manage_role(AppRole.MANAGER)
    assert not programmer.can_manage_role(AppRole.CASHIER)
    assert not programmer.can_manage_role(AppRole.PROGRAMMER)

def test_owner_has_full_business_and_employee_management():
    owner = UserContext(user_id="o1", username="owner", role=AppRole.OWNER)

    assert owner.has_permission(Permission.EMPLOYEES_MANAGE)
    assert owner.has_permission(Permission.ANALYTICS_READ)
    assert owner.has_permission(Permission.AI_QUERY_BUSINESS)
    assert owner.has_permission(Permission.BILLING_CREATE)
    assert owner.has_permission(Permission.BILLING_READ)
    assert owner.has_permission(Permission.BILLING_MANAGE)
    assert owner.has_permission(Permission.PRODUCTS_MANAGE)
    assert owner.has_permission(Permission.INVENTORY_MANAGE)
    assert owner.has_permission(Permission.SUPPLIERS_MANAGE)
    assert owner.has_permission(Permission.PURCHASES_MANAGE)

    assert owner.can_manage_role(AppRole.MANAGER)
    assert owner.can_manage_role(AppRole.CASHIER)
    assert owner.can_manage_role(AppRole.PROGRAMMER)

def test_manager_permissions():
    manager = UserContext(user_id="m1", username="mgr", role=AppRole.MANAGER)

    assert manager.has_permission(Permission.BILLING_CREATE)
    assert manager.has_permission(Permission.BILLING_READ)
    assert manager.has_permission(Permission.BILLING_MANAGE)
    assert manager.has_permission(Permission.PRODUCTS_MANAGE)
    assert manager.has_permission(Permission.INVENTORY_MANAGE)
    assert manager.has_permission(Permission.PURCHASES_MANAGE)
    assert manager.has_permission(Permission.ANALYTICS_READ)
    assert manager.has_permission(Permission.AI_QUERY_BUSINESS)

    assert not manager.has_permission(Permission.EMPLOYEES_MANAGE)
    assert not manager.has_permission(Permission.SYSTEM_HEALTH_MONITOR)
    assert not manager.can_manage_role(AppRole.OWNER)

def test_cashier_permissions():
    cashier = UserContext(user_id="c1", username="cashier1", role=AppRole.CASHIER)

    assert cashier.has_permission(Permission.BILLING_CREATE)
    assert cashier.has_permission(Permission.BILLING_READ)
    assert cashier.has_permission(Permission.PRODUCTS_READ)
    assert cashier.has_permission(Permission.INVENTORY_READ)

    assert not cashier.has_permission(Permission.PRODUCTS_MANAGE)
    assert not cashier.has_permission(Permission.INVENTORY_MANAGE)
    assert not cashier.has_permission(Permission.SUPPLIERS_READ)
    assert not cashier.has_permission(Permission.PURCHASES_READ)
    assert not cashier.has_permission(Permission.ANALYTICS_READ)
    assert not cashier.has_permission(Permission.AI_QUERY_BUSINESS)
    assert not cashier.has_permission(Permission.EMPLOYEES_MANAGE)
    assert not cashier.has_permission(Permission.SYSTEM_HEALTH_MONITOR)

