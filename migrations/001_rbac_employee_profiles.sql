
-- ============================================================================
-- Retail Sales Intelligence Platform
-- Production Supabase Authentication & RBAC Schema
-- Version: 2026.11.08-security-hardened-rbac-v2
--
-- Roles:
--   owner       - Full business administration
--   manager     - Shop operations and analytics
--   cashier     - POS and limited billing access
--   programmer  - Technical maintenance, no default financial access
--
-- Security:
--   1. Employee profiles linked to auth.users
--   2. Four-role CHECK constraint
--   3. RLS on employee_profiles and technical_audit_logs
--   4. SECURITY DEFINER role helper with empty search_path
--   5. Explicit table privileges
--   6. Audit logs are read-only for authenticated clients
--   7. Backend service role performs trusted administrative operations
--
-- IMPORTANT:
--   Keep SUPABASE_SERVICE_ROLE_KEY exclusively on the backend.
--   FastAPI must independently enforce RBAC.
-- ============================================================================


-- ============================================================================
-- 1. EMPLOYEE PROFILES
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.employee_profiles (
    id UUID PRIMARY KEY
        REFERENCES auth.users(id)
        ON DELETE CASCADE,

    full_name TEXT NOT NULL,

    email TEXT,

    role TEXT NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_employee_role
        CHECK (role IN ('owner', 'manager', 'cashier', 'programmer'))
);

CREATE INDEX IF NOT EXISTS idx_employee_profiles_role
    ON public.employee_profiles(role);

CREATE INDEX IF NOT EXISTS idx_employee_profiles_active
    ON public.employee_profiles(is_active);


-- ============================================================================
-- 2. TECHNICAL AND ADMINISTRATIVE AUDIT LOGS
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.technical_audit_logs (
    log_id BIGSERIAL PRIMARY KEY,

    performed_by UUID
        REFERENCES auth.users(id)
        ON DELETE SET NULL,

    action_type TEXT NOT NULL,

    target_resource TEXT,

    details TEXT,

    performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tech_audit_performed_at
    ON public.technical_audit_logs(performed_at);

CREATE INDEX IF NOT EXISTS idx_tech_audit_performed_by
    ON public.technical_audit_logs(performed_by);


-- ============================================================================
-- 3. UPDATED_AT TRIGGER
-- ============================================================================

CREATE OR REPLACE FUNCTION public.update_employee_profile_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_employee_profiles_updated_at
    ON public.employee_profiles;

CREATE TRIGGER trg_employee_profiles_updated_at
    BEFORE UPDATE ON public.employee_profiles
    FOR EACH ROW
    EXECUTE FUNCTION public.update_employee_profile_timestamp();


-- ============================================================================
-- 4. SECURE EMPLOYEE ROLE LOOKUP
--
-- SECURITY DEFINER avoids recursive RLS evaluation.
-- Empty search_path prevents object-shadowing attacks.
-- Fully qualified table references are used.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_auth_employee_role()
RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT ep.role
    FROM public.employee_profiles AS ep
    WHERE ep.id = auth.uid()
      AND ep.is_active = TRUE
    LIMIT 1;
$$;

-- Restrict execution privileges.

REVOKE ALL
    ON FUNCTION public.get_auth_employee_role()
    FROM PUBLIC;

REVOKE ALL
    ON FUNCTION public.get_auth_employee_role()
    FROM anon;

GRANT EXECUTE
    ON FUNCTION public.get_auth_employee_role()
    TO authenticated;


-- ============================================================================
-- 5. ENABLE ROW LEVEL SECURITY
-- ============================================================================

ALTER TABLE public.employee_profiles
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.technical_audit_logs
    ENABLE ROW LEVEL SECURITY;


-- ============================================================================
-- 6. EMPLOYEE PROFILE POLICIES
-- ============================================================================

-- Employees can read their own profile.
-- Owners can read all employee profiles.

DROP POLICY IF EXISTS
    "Allow user to read own profile or owner to read all"
    ON public.employee_profiles;

CREATE POLICY
    "Allow user to read own profile or owner to read all"
ON public.employee_profiles
FOR SELECT
TO authenticated
USING (
    id = (SELECT auth.uid())
    OR
    (SELECT public.get_auth_employee_role()) = 'owner'
);


-- Only owners can insert employee profiles.

DROP POLICY IF EXISTS
    "Allow owners to insert employee profiles"
    ON public.employee_profiles;

CREATE POLICY
    "Allow owners to insert employee profiles"
ON public.employee_profiles
FOR INSERT
TO authenticated
WITH CHECK (
    (SELECT public.get_auth_employee_role()) = 'owner'
);


-- Only owners can update employee profiles.

DROP POLICY IF EXISTS
    "Allow owners to update employee profiles"
    ON public.employee_profiles;

CREATE POLICY
    "Allow owners to update employee profiles"
ON public.employee_profiles
FOR UPDATE
TO authenticated
USING (
    (SELECT public.get_auth_employee_role()) = 'owner'
)
WITH CHECK (
    (SELECT public.get_auth_employee_role()) = 'owner'
);


-- Only owners can delete employee profiles.

DROP POLICY IF EXISTS
    "Allow owners to delete employee profiles"
    ON public.employee_profiles;

CREATE POLICY
    "Allow owners to delete employee profiles"
ON public.employee_profiles
FOR DELETE
TO authenticated
USING (
    (SELECT public.get_auth_employee_role()) = 'owner'
);


-- ============================================================================
-- 7. AUDIT LOG POLICIES
-- ============================================================================

-- Only owners and programmers can read audit logs.

DROP POLICY IF EXISTS
    "Allow owners and programmers to view audit logs"
    ON public.technical_audit_logs;

CREATE POLICY
    "Allow owners and programmers to view audit logs"
ON public.technical_audit_logs
FOR SELECT
TO authenticated
USING (
    (SELECT public.get_auth_employee_role())
    IN ('owner', 'programmer')
);


-- Explicitly deny authenticated client INSERT operations.

DROP POLICY IF EXISTS
    "Disallow client-side audit insertions"
    ON public.technical_audit_logs;

CREATE POLICY
    "Disallow client-side audit insertions"
ON public.technical_audit_logs
FOR INSERT
TO authenticated
WITH CHECK (FALSE);


-- Explicitly deny authenticated client UPDATE operations.

DROP POLICY IF EXISTS
    "Disallow audit modifications"
    ON public.technical_audit_logs;

CREATE POLICY
    "Disallow audit modifications"
ON public.technical_audit_logs
FOR UPDATE
TO authenticated
USING (FALSE)
WITH CHECK (FALSE);


-- Explicitly deny authenticated client DELETE operations.

DROP POLICY IF EXISTS
    "Disallow audit deletions"
    ON public.technical_audit_logs;

CREATE POLICY
    "Disallow audit deletions"
ON public.technical_audit_logs
FOR DELETE
TO authenticated
USING (FALSE);


-- ============================================================================
-- 8. EXPLICIT TABLE PRIVILEGES
--
-- RLS controls row access; GRANT/REVOKE controls table access.
-- Backend service_role operations bypass RLS and must be authorized by FastAPI.
-- ============================================================================

REVOKE ALL ON TABLE public.employee_profiles FROM PUBLIC;
REVOKE ALL ON TABLE public.employee_profiles FROM anon;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE public.employee_profiles
    TO authenticated;

REVOKE ALL ON TABLE public.technical_audit_logs FROM PUBLIC;
REVOKE ALL ON TABLE public.technical_audit_logs FROM anon;

GRANT SELECT
    ON TABLE public.technical_audit_logs
    TO authenticated;

-- Sequence permissions are not granted to authenticated clients.
-- Backend service_role can perform trusted inserts.


-- ============================================================================
-- 9. FUNCTION EXECUTION PRIVILEGES
-- ============================================================================

REVOKE ALL
    ON FUNCTION public.update_employee_profile_timestamp()
    FROM PUBLIC;

REVOKE ALL
    ON FUNCTION public.update_employee_profile_timestamp()
    FROM anon;

REVOKE ALL
    ON FUNCTION public.update_employee_profile_timestamp()
    FROM authenticated;


-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
