"""
Data-Dive API — Content Creator Analytics Engine
FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.routers.content import router as content_router
from app.routers.auth import router as auth_router
from app.routers.metrics import router as metrics_router
from app.routers.analytics import router as analytics_router
from app.routers.ideas import router as ideas_router
from app.routers.kanban import router as kanban_router
from app.routers.telemetry import router as telemetry_router
from app.routers.projects import router as projects_router
from app.middleware.usage import UsageTrackingMiddleware
from app.services.telemetry.service import get_hub
from app.core.redis import (
    init_redis_pool,
    close_redis_pool,
    check_redis_health,
)

logger = logging.getLogger("datadive.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    settings = get_settings()
    print(f"🚀 {settings.app_name} starting...")
    print(f"   Mock Mode: {'ON' if settings.mock_mode else 'OFF'}")
    print(f"   Frontend URL: {settings.frontend_url}")

    # Database initialization
    if not settings.mock_mode:
        from app.db.session import init_db
        await init_db()
        print("   Database: Connected & tables created")
    else:
        print("   Database: Skipped (mock mode)")

    # Redis broker initialization
    try:
        await init_redis_pool(settings.redis_url)
        print("   Redis: Connected")
    except Exception as exc:
        # Log but don't crash — API can still serve non-queued endpoints
        logger.warning("Redis init failed — task dispatch unavailable: %s", exc)
        print(f"   Redis: UNAVAILABLE ({exc})")

    # Usage tracking hub (buffer + background flush to db/log/webhook/otlp)
    hub = get_hub()
    hub.start()
    print(f"   Telemetry: {'ON' if settings.telemetry_enabled else 'OFF'} → {', '.join(settings.telemetry_sink_list)}")

    yield

    # Shutdown: release all connections
    await hub.stop()
    await close_redis_pool()
    if not settings.mock_mode:
        from app.db.session import dispose_engine
        await dispose_engine()
    print(f"👋 {settings.app_name} shutting down...")


app = FastAPI(
    title="Data-Dive API",
    description="Content Creator Data-First Analytics Engine",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS configuration
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Usage tracking (must be added before CORS so it wraps the actual handlers; never raises)
app.add_middleware(UsageTrackingMiddleware)

# Include routers
app.include_router(content_router)
app.include_router(auth_router)
app.include_router(metrics_router)
app.include_router(analytics_router)
app.include_router(ideas_router)
app.include_router(kanban_router)
app.include_router(telemetry_router)
app.include_router(projects_router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint with Redis status."""
    redis_healthy = await check_redis_health()
    return {
        "status": "healthy",
        "service": "Data-Dive API",
        "version": "0.3.0",
        "mock_mode": settings.mock_mode,
        "redis": "connected" if redis_healthy else "unavailable",
    }
