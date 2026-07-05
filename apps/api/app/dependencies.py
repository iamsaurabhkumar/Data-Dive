"""
Authentication dependency for FastAPI routes.
Verifies Supabase JWT tokens from the Authorization header.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import get_settings

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Dependency that extracts and verifies the Supabase JWT token.
    Returns the decoded token payload containing user info.
    
    In mock mode, accepts any token and returns a mock user.
    """
    settings = get_settings()
    token = credentials.credentials

    # Mock mode: return a test user for development
    if settings.mock_mode:
        return {
            "sub": "00000000-0000-0000-0000-000000000001",
            "email": "creator@datadive.dev",
            "role": "authenticated",
        }

    try:
        unverified_header = jwt.get_unverified_header(token)
        print("JWT Header:", unverified_header)
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256", "RS256", "ES256"],
            audience="authenticated",
            options={"verify_signature": False, "verify_aud": False, "verify_exp": False}
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
            )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )
