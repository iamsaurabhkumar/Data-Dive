"""
Auth API router.
Handles platform connection status and creator profile.
"""
from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from app.config import get_settings
from app.schemas import CreatorProfileSchema
from app.services.mock_data import get_mock_creator_profile

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/profile", response_model=CreatorProfileSchema)
async def get_profile(
    user: dict = Depends(get_current_user),
):
    """Get the current creator's profile with platform connection status."""
    settings = get_settings()

    if settings.mock_mode:
        profile = get_mock_creator_profile()
        profile["email"] = user.get("email", "creator@datadive.dev")
        return CreatorProfileSchema(**profile)

    # TODO: Fetch from database
    return CreatorProfileSchema(**get_mock_creator_profile())


@router.post("/connect/{platform}")
async def connect_platform(
    platform: str,
    user: dict = Depends(get_current_user),
):
    """
    Connect a platform (YouTube or Instagram).
    In production, this stores the provider_token from Supabase OAuth.
    """
    settings = get_settings()
    platform_lower = platform.lower()

    if platform_lower not in ("youtube", "instagram"):
        return {"error": f"Unsupported platform: {platform}"}

    if settings.mock_mode:
        return {
            "success": True,
            "platform": platform,
            "message": f"Mock connection to {platform} established.",
        }

    # TODO: Store provider_token and fetch initial content
    return {
        "success": True,
        "platform": platform,
        "message": f"Connected to {platform}. Initial sync starting...",
    }
