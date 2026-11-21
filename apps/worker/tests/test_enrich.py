"""
enrich_idea against a real (migrated) Postgres with a fake OpenAI client.
    TEST_DATABASE_URL=postgresql+asyncpg://... pytest apps/worker/tests
"""
import json
import os
import sys
import uuid
from types import SimpleNamespace

import pytest

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")

if DB_URL:
    os.environ["DATABASE_URL"] = DB_URL
    os.environ.setdefault("OPENAI_API_KEY", "test-key")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeParse:
    def __init__(self, fail=False):
        self.fail, self.messages = fail, None

    async def parse(self, model, messages, response_format):
        self.messages = messages
        if self.fail:
            import httpx, openai
            raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))
        parsed = response_format(title="Polished title", hook="Polished hook.", outline=["a", "b", "c", "d"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])


def fake_client(fail=False):
    p = FakeParse(fail)
    return SimpleNamespace(beta=SimpleNamespace(chat=SimpleNamespace(completions=p))), p


async def _seed():
    from sqlalchemy import text
    from db import get_session
    cid, sid, tid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with get_session() as s:
        await s.execute(text("INSERT INTO creator_profiles (id, user_id) VALUES (:c, :c)"), {"c": cid})
        await s.execute(text("""INSERT INTO platform_trends (id, source, category, title, external_url, raw_metadata)
                                VALUES (:t, 'youtube', 'tech', 'Invisible cut transition', :u, CAST(:m AS jsonb))"""),
                        {"t": tid, "u": f"https://x/{tid}", "m": json.dumps({"tags": ["transitions", "editing"]})})
        await s.execute(text("""INSERT INTO content_suggestions (id, creator_id, trend_id, title, description, status,
                                source, platform, content_type, topics, enrichment_status)
                                VALUES (:s, :c, :t, 'Raw title', 'd', 'pending', 'trend', 'Instagram', 'Reel',
                                        CAST('["transitions"]' AS jsonb), 'queued')"""), {"s": sid, "c": cid, "t": tid})
    return str(sid)


async def _row(sid):
    from sqlalchemy import text
    from db import get_session
    async with get_session() as s:
        return (await s.execute(text("SELECT title, hook, outline, enrichment_status FROM content_suggestions WHERE id=:i"), {"i": sid})).first()


@pytest.mark.asyncio
async def test_enrich_success_uses_trend_context():
    import tasks
    sid = await _seed()
    client, parse = fake_client()
    out = await tasks.enrich_idea({"openai": client, "job_try": 1}, sid)
    assert out["status"] == "success"
    row = await _row(sid)
    assert row.title == "Polished title" and row.hook == "Polished hook." and row.enrichment_status == "done"
    assert "Invisible cut transition" in parse.messages[1]["content"]  # trend context reached the prompt
    from db import engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_enrich_retries_then_marks_failed():
    import tasks
    from arq import Retry
    sid = await _seed()
    client, _ = fake_client(fail=True)
    with pytest.raises(Retry):
        await tasks.enrich_idea({"openai": client, "job_try": 1}, sid)
    assert (await _row(sid)).enrichment_status == "queued"
    out = await tasks.enrich_idea({"openai": client, "job_try": tasks.ENRICH_MAX_TRIES}, sid)
    assert out["status"] == "failed" and (await _row(sid)).enrichment_status == "failed"
    from db import engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_enrich_without_key_is_skipped(monkeypatch):
    import tasks
    sid = await _seed()
    monkeypatch.setattr(tasks._settings, "openai_api_key", "")
    client, _ = fake_client()
    assert (await tasks.enrich_idea({"openai": client}, sid))["status"] == "skipped"
    assert (await _row(sid)).enrichment_status == "skipped"
    from db import engine
    await engine.dispose()
