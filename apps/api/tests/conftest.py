import os

os.environ.setdefault("MOCK_MODE", "true")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1/0")  # unreachable on purpose: API must still boot
os.environ.setdefault("TELEMETRY_SINKS", "db")                 # keep test output quiet
os.environ.setdefault("TELEMETRY_FLUSH_SECONDS", "0.1")

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.services.analytics.engine import Analysis
from app.services.analytics.records import PostRecord
from app.services.mock_data import MOCK_NOW, get_mock_feed


@pytest.fixture(scope="session")
def posts():
    return [PostRecord.from_feed_dict(p) for p in get_mock_feed()]


@pytest.fixture
def analysis(posts):
    return Analysis(posts, now=MOCK_NOW)


@pytest.fixture
def client():
    get_settings.cache_clear()
    from app.routers import deps
    deps.reset_memory_repo()
    from app.services.telemetry.service import reset_hub
    reset_hub()
    from app.main import app
    with TestClient(app) as c:
        c.headers.update({"Authorization": "Bearer test"})
        yield c
