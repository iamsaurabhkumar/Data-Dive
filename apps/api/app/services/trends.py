"""
Load current trends for the "Generate Next Project" engine.

Mock mode → deterministic demo trends. DB mode → recent rows of platform_trends
(written by the worker's 12-hour cycle), selected column-by-column so the
pgvector embedding never has to be decoded here.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.analytics.trends import TrendRecord, mock_trends
from app.services.mock_data import MOCK_NOW

_SQL = text("""
    SELECT id, source, category, title, description, external_url, raw_metadata, fetched_at
    FROM platform_trends
    WHERE fetched_at > now() - interval '7 days'
      AND (expires_at IS NULL OR expires_at > now())
    ORDER BY fetched_at DESC
    LIMIT 200
""")


async def load_trends(db: Optional[AsyncSession]) -> List[TrendRecord]:
    if get_settings().mock_mode or db is None:
        return mock_trends(MOCK_NOW)
    rows = (await db.execute(_SQL)).mappings().all()
    return [TrendRecord.from_row(dict(r)) for r in rows]
