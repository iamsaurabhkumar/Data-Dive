from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "Data-Dive API"
    debug: bool = True
    mock_mode: bool = True  # Use mock data for development

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""

    # Database
    database_url: str = ""

    # YouTube API (optional - only needed when mock_mode is False)
    google_client_id: str = ""
    google_client_secret: str = ""

    # Meta/Instagram API (optional - only needed when mock_mode is False)
    meta_app_id: str = ""
    meta_app_secret: str = ""

    # CORS
    frontend_url: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
