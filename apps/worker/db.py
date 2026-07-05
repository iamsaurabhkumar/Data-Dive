"""
Independent async database session factory for the worker process.

WHY this exists separately from apps/api/app/db/session.py:
- The worker is a completely separate Docker container and Python process.
- It must own its own connection pool to prevent cross-service pool exhaustion.
- Pool is intentionally small (3+5) — worker executes sequential tasks, not concurrent HTTP requests.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from config import get_worker_settings

logger = logging.getLogger("datadive.worker.db")

_settings = get_worker_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=5,
    pool_recycle=1800,   # Recycle connections every 30 min to avoid Supabase idle timeouts
    pool_timeout=10,
)

session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Scoped async session for worker tasks.
    Each task gets its own session — commit on success, rollback on failure.
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Worker DB session rolled back")
            raise
        finally:
            await session.close()
