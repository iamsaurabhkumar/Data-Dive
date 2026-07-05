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

    yield

    # Shutdown: release all connections
    await close_redis_pool()
    print(f"👋 {settings.app_name} shutting down...")


app = FastAPI(
    title="Data-Dive API",
    description="Content Creator Data-First Analytics Engine",
    version="0.2.0",
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

# Include routers
app.include_router(content_router)
app.include_router(auth_router)
app.include_router(metrics_router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint with Redis status."""
    redis_healthy = await check_redis_health()
    return {
        "status": "healthy",
        "service": "Data-Dive API",
        "version": "0.2.0",
        "mock_mode": settings.mock_mode,
        "redis": "connected" if redis_healthy else "unavailable",
    }
