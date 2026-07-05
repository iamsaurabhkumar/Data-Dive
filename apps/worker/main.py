"""
Data-Dive ARQ Worker — Entry Point

This module defines the ARQ WorkerSettings class that configures:
- Redis connection for task consumption
- Registered task functions
- Cron schedules for automated polling cycles
- Retry policies with exponential backoff
"""
import logging
import httpx
import openai
from datetime import timedelta
from typing import Any

from arq import cron, func
from arq.connections import RedisSettings
from config import get_worker_settings

# Import business logic tasks
from tasks import fetch_and_analyze_trends

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("datadive.worker")

_settings = get_worker_settings()


# ──────────────────────────────────────────────
# Task Handlers
# ──────────────────────────────────────────────

async def heartbeat(ctx: dict[str, Any]) -> str:
    logger.info("💓 Worker heartbeat — alive and listening")
    return "ok"


async def process_sync_task(ctx: dict[str, Any], creator_id: str, provider_token: str | None = None) -> dict:
    logger.info("Processing sync task for creator_id=%s", creator_id)
    return {"status": "completed", "creator_id": creator_id}

# ──────────────────────────────────────────────
# Startup / Shutdown Hooks
# ──────────────────────────────────────────────

async def startup(ctx: dict[str, Any]) -> None:
    logger.info("🚀 Data-Dive Worker starting up...")
    
    # Initialize httpx AsyncClient for connection reuse
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    ctx['http'] = httpx.AsyncClient(limits=limits, timeout=10.0)
    
    # Initialize OpenAI AsyncClient
    # Uses api_key from environment implicitly, or we can explicitly pass it from settings
    ctx['openai'] = openai.AsyncClient(api_key=_settings.openai_api_key)

async def shutdown(ctx: dict[str, Any]) -> None:
    # Close HTTP client
    if 'http' in ctx:
        await ctx['http'].aclose()
        
    # Close OpenAI client
    if 'openai' in ctx:
        await ctx['openai'].close()
        
    # Dispose DB connections
    from db import engine
    await engine.dispose()
    
    logger.info("👋 Data-Dive Worker shut down")

# ──────────────────────────────────────────────
# ARQ WorkerSettings
# ──────────────────────────────────────────────

def _parse_redis_settings() -> RedisSettings:
    url = _settings.redis_url
    url = url.replace("redis://", "")
    parts = url.split("/")
    host_port = parts[0]
    database = int(parts[1]) if len(parts) > 1 else 0

    if ":" in host_port:
        host, port = host_port.split(":")
        port = int(port)
    else:
        host = host_port
        port = 6379

    return RedisSettings(host=host, port=port, database=database)

class WorkerSettings:
    """ARQ worker configuration."""

    redis_settings = _parse_redis_settings()

    functions = [
        # Per-task configuration
        func(fetch_and_analyze_trends, max_tries=4, timeout=120),
        process_sync_task,
    ]

    cron_jobs = [
        cron(heartbeat, second=0),
    ]

    on_startup = startup
    on_shutdown = shutdown

    max_jobs = 5
    keep_result = timedelta(hours=1)
