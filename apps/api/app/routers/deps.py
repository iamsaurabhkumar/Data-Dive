"""
Shared dependencies for the Phase 3 routers.

get_planning_service() resolves: current user → creator id → posts (mock or DB)
→ repository (memory or SQL) → PlanningService.
"""
from __future__ import annotations

from typing import AsyncGenerator, Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.dependencies import get_current_user
from app.repositories.memory import MemoryPlanningRepository
from app.repositories.sql import SqlPlanningRepository
from app.services.mock_data import MOCK_NOW
from app.services.mock_planning import seed_mock_planning
from app.services.planning import PlanningService
from app.services.posts import ensure_creator_profile, load_posts

_memory_repo: Optional[MemoryPlanningRepository] = None


def get_memory_repo() -> MemoryPlanningRepository:
    global _memory_repo
    if _memory_repo is None:
        _memory_repo = MemoryPlanningRepository(seeder=seed_mock_planning)
    return _memory_repo


def reset_memory_repo() -> None:
    """Test helper."""
    global _memory_repo
    _memory_repo = None


async def get_planning_service(
    user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
) -> AsyncGenerator[PlanningService, None]:
    settings = get_settings()
    if settings.mock_mode or db is None:
        creator_id = user["sub"]
        posts = await load_posts(None, creator_id)
        yield PlanningService(get_memory_repo(), creator_id, posts, tz=settings.creator_timezone, now=MOCK_NOW)
        return

    creator_id = await ensure_creator_profile(db, user["sub"])
    posts = await load_posts(db, creator_id)
    yield PlanningService(SqlPlanningRepository(db), creator_id, posts, tz=settings.creator_timezone)
