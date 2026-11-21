"""
Authentication dependency for FastAPI routes.
Verifies Supabase JWT tokens from the Authorization header.
"""
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import get_settings

logger = logging.getLogger("datadive.auth")

# auto_error=False so that a missing header yields 401 (not 403) with a clear message
security = HTTPBearer(auto_error=False)

MOCK_USER = {
    "sub": "00000000-0000-0000-0000-000000000001",
    "email": "creator@datadive.dev",
    "role": "authenticated",
}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """
    Extract and verify the Supabase JWT.

    - Mock mode: any (or no) token maps to a single demo user.
    - Real mode: signature, expiry and audience are verified against
      SUPABASE_JWT_SECRET (HS256 — Supabase's default signing scheme).
    """
    settings = get_settings()

    if settings.mock_mode:
        return dict(MOCK_USER)

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not settings.supabase_jwt_secret:
        # Misconfiguration must fail closed, never open.
        logger.error("SUPABASE_JWT_SECRET is not configured; refusing to authenticate")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication is not configured on the server",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user ID",
        )
    return payload
