from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Data-Dive API"
    debug: bool = False  # echo SQL etc. Never default to True (leaks query params into logs)
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

    # Redis broker
    redis_url: str = "redis://localhost:6379/0"

    # Analytics / planning
    creator_timezone: str = "UTC"  # default timezone for posting-time analysis
    mock_seed: int = 42            # seed for deterministic mock data

    # "Generate Next Project": queue an LLM polish pass in the worker (needs Redis + OPENAI_API_KEY on the worker)
    ai_enrichment_enabled: bool = True

    # Usage tracking / telemetry
    telemetry_enabled: bool = True
    telemetry_sinks: str = "db,log"          # comma-separated: db | log | webhook | otlp
    telemetry_flush_seconds: float = 5.0
    telemetry_max_buffer: int = 200
    telemetry_hash_salt: str = "change-me"    # salts the creator id in exported payloads
    telemetry_webhook_url: str = ""
    telemetry_webhook_token: str = ""
    telemetry_otlp_endpoint: str = ""         # e.g. http://otel-collector:4318/v1/logs
    telemetry_otlp_headers: str = ""          # "key=value,key2=value2"
    admin_user_ids: str = ""                  # comma-separated Supabase user ids allowed to read scope=all

    # Feedback / surveys
    feedback_min_uses: int = 3
    feedback_cooldown_days: int = 30
    feedback_dismiss_cooldown_days: int = 7
    feedback_max_prompts_per_day: int = 1

    @property
    def telemetry_sink_list(self) -> list[str]:
        return [s.strip().lower() for s in self.telemetry_sinks.split(",") if s.strip()]

    @property
    def admin_ids(self) -> set[str]:
        return {s.strip() for s in self.admin_user_ids.split(",") if s.strip()}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
