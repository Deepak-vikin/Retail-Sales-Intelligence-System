import os
import json
import time
from typing import Optional, Callable, Dict, Any
import jwt
from jwt import PyJWKClient, PyJWKClientError
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.permissions import AppRole, Permission, UserContext, ROLE_PERMISSIONS
from app.core.config import (
    SUPABASE_URL,
    SUPABASE_JWKS_URL,
    SUPABASE_JWT_SECRET,
)
from app.core.database import connection

bearer_scheme = HTTPBearer(auto_error=False)

_jwks_client: Optional[PyJWKClient] = None

def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            uri=SUPABASE_JWKS_URL,
            cache_keys=True,
            max_cached_keys=16,
            cache_jwk_set=True,
            lifespan=3600,
        )
    return _jwks_client

def set_jwks_client(client: PyJWKClient):
    global _jwks_client
    _jwks_client = client

def verify_supabase_jwt(token: str) -> Dict[str, Any]:
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Malformed JWT header: {str(e)}"
        )

    alg = unverified_header.get("alg")
    kid = unverified_header.get("kid")

    if not alg:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT header missing 'alg' parameter."
        )

    expected_issuer = f"{SUPABASE_URL.rstrip('/')}/auth/v1"
    expected_audience = "authenticated"

    if alg in ["ES256", "RS256"]:
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Asymmetric {alg} token missing 'kid' header."
            )

        jwks_client = get_jwks_client()
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
        except PyJWKClientError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unknown or rotated key ID '{kid}': {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Failed to fetch public key for key ID '{kid}': {str(e)}"
            )

        try:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                issuer=expected_issuer,
                audience=expected_audience,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_sub": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired. Please log in again."
            )
        except jwt.InvalidSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token signature. Authentication failed."
            )
        except jwt.InvalidIssuerError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token issuer. Expected '{expected_issuer}'."
            )
        except jwt.InvalidAudienceError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token audience. Expected '{expected_audience}'."
            )
        except jwt.MissingRequiredClaimError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Missing required claim in token: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid authentication token: {str(e)}"
            )

    elif alg == "HS256":
        if not SUPABASE_JWT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Legacy symmetric HS256 tokens are not supported on this project. Key is asymmetric ES256."
            )

        try:
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                issuer=expected_issuer,
                audience=expected_audience,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_sub": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired. Please log in again."
            )
        except jwt.InvalidSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid legacy token signature. Authentication failed."
            )
        except jwt.InvalidIssuerError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token issuer. Expected '{expected_issuer}'."
            )
        except jwt.InvalidAudienceError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token audience. Expected '{expected_audience}'."
            )
        except jwt.MissingRequiredClaimError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Missing required claim in token: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid legacy token: {str(e)}"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unsupported JWT signing algorithm '{alg}'. Supported algorithms are ES256 (JWKS) and HS256 (legacy)."
        )

_employee_lookup_override: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None

def set_employee_lookup_override(fn: Optional[Callable[[str], Optional[Dict[str, Any]]]]):
    global _employee_lookup_override
    _employee_lookup_override = fn

def get_employee_from_db(user_uuid: str) -> Optional[Dict[str, Any]]:
    if _employee_lookup_override is not None:
        return _employee_lookup_override(user_uuid)
    try:
        conn = connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, full_name, email, role, is_active FROM employee_profiles WHERE id = %s;",
            (user_uuid,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {
                "id": str(row[0]),
                "full_name": row[1],
                "email": row[2],
                "role": row[3],
                "is_active": row[4],
            }
    except Exception:
        pass
    return None

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> UserContext:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Bearer token required."
        )

    token = credentials.credentials
    payload = verify_supabase_jwt(token)

    user_uuid = payload.get("sub")
    if not user_uuid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token: missing 'sub' subject claim."
        )

    # Strictly retrieve employee profile from employee_profiles table (database-backed role).
    # Never trust user_metadata or app_metadata supplied by client/unverified claims.
    profile = get_employee_from_db(user_uuid)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User '{user_uuid}' does not have an active employee profile. Contact the store owner to be onboarded."
        )

    if not profile.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact store owner."
        )

    try:
        role_enum = AppRole(profile["role"].lower())
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid employee role: '{profile.get('role')}'"
        )

    return UserContext(
        user_id=profile["id"],
        email=profile.get("email"),
        full_name=profile.get("full_name"),
        role=role_enum,
        is_active=True,
    )

def require_permission(permission: Permission) -> Callable[[UserContext], UserContext]:
    def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        if not user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{user.role.value}' lacks required permission '{permission.value}'."
            )
        return user
    return dependency

def require_role(*allowed_roles: AppRole) -> Callable[[UserContext], UserContext]:
    def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        if user.role not in allowed_roles:
            role_names = [r.value for r in allowed_roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{user.role.value}' is not authorized. Allowed roles: {role_names}."
            )
        return user
    return dependency

def require_owner(user: UserContext = Depends(get_current_user)) -> UserContext:
    if user.role != AppRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Only shop 'owner' can perform employee management or assign roles."
        )
    return user
