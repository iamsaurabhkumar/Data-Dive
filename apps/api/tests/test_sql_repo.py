"""
DB-mode integration tests. Run only when TEST_DATABASE_URL points at a migrated Postgres.
    TEST_DATABASE_URL="postgresql+asyncpg://postgres@/dd_test?host=/tmp&port=5444" pytest tests/test_sql_repo.py
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import ContentPost, CreatorProfile, MetricSnapshot

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


async def seed_creator(session, n_posts=8):
    uid = uuid.uuid4()
    session.add(CreatorProfile(id=uid, user_id=uid))
    await session.flush()
    now = datetime.now(timezone.utc)
    for i in range(n_posts):
        ct = "Short" if i % 2 else "Long-form"
        post = ContentPost(creator_id=uid, platform="YouTube", external_post_id=f"v{uuid.uuid4().hex[:8]}",
                           title=f"Editing tips {i}" if i % 3 else f"Studio vlog {i}", content_type=ct,
                           published_at=now - timedelta(days=3 * i + 1, hours=i))
        session.add(post)
        await session.flush()
        # two snapshots: the loader must pick the latest
        session.add(MetricSnapshot(post_id=post.id, views=100, likes=1, comments=0,
                                   captured_at=now - timedelta(days=2)))
        session.add(MetricSnapshot(post_id=post.id, views=(i + 1) * 1000, likes=(i + 1) * 50, comments=i,
                                   captured_at=now - timedelta(hours=1)))
    await session.flush()
    return str(uid)


@pytest.mark.asyncio
async def test_load_posts_uses_latest_snapshot(session, monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.services.posts import load_posts
    cid = await seed_creator(session)
    posts = await load_posts(session, cid)
    assert len(posts) == 8
    assert all(p.views >= 1000 for p in posts)  # not the stale 100-view snapshot
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_sql_repository_roundtrip(session, monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.repositories.sql import SqlPlanningRepository
    from app.services.planning import PlanningService
    from app.services.posts import load_posts

    cid = await seed_creator(session)
    other = await seed_creator(session, 2)
    posts = await load_posts(session, cid)
    svc = PlanningService(SqlPlanningRepository(session), cid, posts)

    ideas = await svc.generate_ideas(4, seed=0)
    assert len(ideas) == 4
    assert len(await svc.list_ideas("pending")) == 4

    card = await svc.idea_to_board(ideas[0].id)
    assert card.stage == "idea" and (await svc.list_ideas("converted_to_kanban"))[0].id == ideas[0].id
    card = await svc.move_card(card.id, "scripting")
    card = await svc.move_card(card.id, "published")
    target = posts[0]
    card = await svc.link_post(card.id, target.id)
    view = await svc.review_card(card.id)
    assert view["stage"] == "reviewed" and view["review"]["verdict"]
    learn = await svc.learning()
    assert learn["accuracy"]["count"] == 1 and learn["calibrations"][0]["samples"] == 1

    detail = await svc.card_detail(card.id)
    assert [e["to_stage"] for e in detail["events"]] == ["idea", "scripting", "published", "published", "reviewed"]

    # Tenant isolation: the other creator sees nothing
    other_svc = PlanningService(SqlPlanningRepository(session), other, await load_posts(session, other))
    assert await other_svc.list_ideas() == []
    assert (await other_svc.board())["total"] == 0
    with pytest.raises(LookupError):
        await other_svc.get_card(card.id)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_sql_telemetry_repository(session, monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.repositories.telemetry import SqlTelemetryRepository
    from app.services.telemetry.models import FeatureFeedback, SurveyPromptRecord, UsageEvent

    cid = await seed_creator(session, 1)
    repo = SqlTelemetryRepository(session)
    # events for a creator that does not exist yet must not break the batch
    n = await repo.add_events([
        UsageEvent(name="feature_used", feature="ideas", creator_id=cid, action="generate", session_id="s"),
        UsageEvent(name="api_call", feature="ideas", creator_id=str(uuid.uuid4()), action="view", duration_ms=5, status=200),
    ])
    assert n == 2
    assert await repo.count_feature_uses(cid, "ideas") == 1
    assert len(await repo.list_events(cid, datetime.now(timezone.utc) - timedelta(days=1))) == 1
    assert len(await repo.list_events(None, datetime.now(timezone.utc) - timedelta(days=1))) >= 2

    await repo.add_feedback(FeatureFeedback(creator_id=cid, feature="ideas", rating=5, worth_it="yes", improvement="👍 more"))
    assert (await repo.last_feedback_at(cid, "ideas")) is not None
    assert (await repo.list_feedback(cid, datetime.now(timezone.utc) - timedelta(days=1)))[0].improvement == "👍 more"

    await repo.add_prompt(SurveyPromptRecord(creator_id=cid, feature="board"))
    await repo.mark_dismissed(cid, "board")
    ps = await repo.prompts(cid, datetime.now(timezone.utc) - timedelta(days=1))
    assert len(ps) == 1 and ps[0].dismissed is True

    assert await repo.is_opted_out(cid) is False
    await repo.set_opt_out(cid, True)
    assert await repo.is_opted_out(cid) is True
    get_settings.cache_clear()


def _client_for(monkeypatch, enqueue):
    """TestClient in DB mode with a signed JWT and a fake ARQ enqueue."""
    from jose import jwt
    from fastapi.testclient import TestClient
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    monkeypatch.setenv("TELEMETRY_SINKS", "db")
    from app.config import get_settings
    get_settings.cache_clear()
    import app.db.session as sess
    sess._engine = None; sess._session_factory = None
    from app.services.telemetry.service import reset_hub
    reset_hub()
    import app.routers.projects as projects
    monkeypatch.setattr(projects, "enqueue_task", enqueue)
    from app.main import app
    uid = str(uuid.uuid4())
    token = jwt.encode({"sub": uid, "aud": "authenticated"}, "test-secret", algorithm="HS256")
    return TestClient(app), {"Authorization": f"Bearer {token}"}, uid


def test_next_project_db_mode_with_trends_and_enrichment(monkeypatch):
    import asyncio
    from sqlalchemy import text as sql_text
    calls = []

    async def fake_enqueue(name, *args, **kwargs):
        calls.append((name, args, kwargs))
        return "job-1"

    client, h, uid = _client_for(monkeypatch, fake_enqueue)

    async def seed_trend():
        engine = create_async_engine(DB_URL)
        async with engine.begin() as conn:
            tid = uuid.uuid4()
            await conn.execute(sql_text("""
                INSERT INTO platform_trends (id, source, category, title, external_url, raw_metadata, fetched_at)
                VALUES (:id, 'youtube', 'tech', 'Editing tips that doubled my retention — tested', :url,
                        CAST(:meta AS jsonb), now() - interval '3 hours')"""),
                {"id": tid, "url": f"https://yt/{tid}", "meta": '{"tags": ["editing", "retention"], "views": 50000, "views_per_hour": 4000}'})
        await engine.dispose()
        return str(tid)

    with client:
        # user with synced posts whose titles share the trend's topic
        async def seed_posts():
            engine = create_async_engine(DB_URL)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as s:
                from app.models import CreatorProfile, ContentPost, MetricSnapshot
                s.add(CreatorProfile(id=uuid.UUID(uid), user_id=uuid.UUID(uid)))
                await s.flush()
                now = datetime.now(timezone.utc)
                for i, title in enumerate(["Editing tips for beginners", "My editing workflow", "Studio tour", "Editing tips part 2"]):
                    p = ContentPost(creator_id=uuid.UUID(uid), platform="YouTube", external_post_id=f"np{uuid.uuid4().hex[:8]}",
                                    title=title, content_type="Long-form", published_at=now - timedelta(days=5 * i + 1))
                    s.add(p); await s.flush()
                    s.add(MetricSnapshot(post_id=p.id, views=(3 if "Editing" in title else 1) * 1000, likes=10))
                await s.commit()
            await engine.dispose()
        asyncio.run(seed_posts())
        tid = asyncio.run(seed_trend())

        d = client.post("/api/projects/next", json={}, headers=h).json()
        assert d["trend"]["trend"]["id"] == tid and "editing" in " ".join(d["trend"]["matched_topics"])
        assert d["enrichment"] == "queued" and d["idea"]["enrichment_status"] == "queued"
        assert calls[-1][0] == "enrich_idea" and calls[-1][1] == (d["idea"]["id"],)
        polled = client.get(f"/api/ideas/{d['idea']['id']}", headers=h).json()
        assert polled["enrichment_status"] == "queued" and polled["trend_id"] == tid and polled["kit"]["shot_list"]

        # the trend is now used: the server must never propose it again (other rows in a shared test DB may
        # still be relevant, so either a different trend or the analytics fallback is acceptable)
        d2 = client.post("/api/projects/next", json={}, headers=h).json()
        assert d2["idea"]["trend_id"] != tid
        assert d2["idea"]["trend_id"] is not None or d2["fallback_reason"] in ("no_relevant_trends", "no_trends")

    from app.config import get_settings
    get_settings.cache_clear()


def test_next_project_db_mode_queue_down(monkeypatch):
    async def broken_enqueue(name, *args, **kwargs):
        from app.core.redis import RedisUnavailableError
        raise RedisUnavailableError("down")

    client, h, uid = _client_for(monkeypatch, broken_enqueue)
    with client:
        d = client.post("/api/projects/next", json={}, headers=h).json()
        assert d["enrichment"] == "unavailable" and d["idea"]["enrichment_status"] is None
        assert client.get(f"/api/ideas/{d['idea']['id']}", headers=h).json()["enrichment_status"] is None
    from app.config import get_settings
    get_settings.cache_clear()
