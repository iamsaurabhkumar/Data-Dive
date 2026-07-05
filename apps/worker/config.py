"""
Worker configuration loaded from environment variables.
Independent from the FastAPI config — this is a separate process.
"""
from pydantic_settings import BaseSettings


class WorkerSettings(BaseSettings):
    """Worker-specific settings."""

    # Redis broker
    redis_url: str = "redis://localhost:6379/0"

    # Database (same remote Supabase instance)
    database_url: str = ""

    # Supabase admin access (for direct writes)
    supabase_url: str = ""
    supabase_service_key: str = ""

    # External API keys (injected by docker-compose)
    openai_api_key: str = ""
    youtube_api_key: str = ""
    apify_api_key: str = ""
    newsapi_key: str = ""
    google_client_id: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()
