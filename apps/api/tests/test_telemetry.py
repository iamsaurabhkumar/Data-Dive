"""Usage tracking, sinks, feedback prompting and the usage summary."""
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import Settings
from app.repositories.telemetry import MemoryTelemetryRepository
from app.services.telemetry.models import FeatureFeedback, InvalidEvent, UsageEvent, clamp_timestamp, hash_creator, sanitize_properties
from app.services.telemetry.service import TelemetryHub, TelemetryService
from app.services.telemetry.sinks import LogSink, WebhookSink
from app.services.telemetry.summary import summarize
from app.services.telemetry.taxonomy import feature_for_route

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def settings(**kw) -> Settings:
    base = dict(mock_mode=True, telemetry_sinks="db", telemetry_flush_seconds=100, telemetry_hash_salt="s")
    base.update(kw)
    return Settings(**base)


# ---- models ------------------------------------------------------------------
def test_event_build_validates_and_sanitizes():
    e = UsageEvent.build("c1", {"feature": "board", "action": "MOVE ", "properties": {"from": "idea", "title": "x" * 500, "nested": {"a": 1}},
                               "page": "/board?x=1", "duration_ms": 12.7, "ts": "2099-01-01T00:00:00Z"}, server_now=NOW)
    assert e.name == "feature_used" and e.action == "move" and e.page == "/board"
    assert len(e.properties["title"]) == 120 and "nested" not in e.properties
    assert e.duration_ms == 12 and e.ts == NOW  # future timestamps are clamped
    assert UsageEvent.build("c1", {"feature": "does-not-exist"}).feature == "other"
    with pytest.raises(InvalidEvent):
        UsageEvent.build("c1", {"name": "bogus", "feature": "board"})
    with pytest.raises(InvalidEvent):
        sanitize_properties({"k": "v" * 120, **{f"k{i}": "v" * 120 for i in range(30)}})


def test_clamp_timestamp_bounds():
    assert clamp_timestamp("garbage", NOW) == NOW
    assert clamp_timestamp((NOW - timedelta(days=30)).isoformat(), NOW) == NOW - timedelta(days=2)
    assert clamp_timestamp((NOW - timedelta(minutes=1)).isoformat(), NOW) == NOW - timedelta(minutes=1)


def test_export_is_anonymized():
    e = UsageEvent(name="feature_used", feature="ideas", creator_id="creator-123", action="generate")
    out = e.export("salt")
    assert "creator_id" not in out and out["creator_hash"] == hash_creator("creator-123", "salt")
    assert hash_creator("creator-123", "salt") != hash_creator("creator-123", "other-salt")
    assert out["type"] == "usage_event"


def test_feature_for_route():
    assert feature_for_route("/api/kanban/cards/{card_id}/review") == "review"
    assert feature_for_route("/api/kanban/board") == "board"
    assert feature_for_route("/api/analytics/learning") == "review"
    assert feature_for_route("/api/analytics/patterns") == "analytics"
    assert feature_for_route("/api/content/sync") == "sync"
    assert feature_for_route("/api/whatever") == "other"


# ---- hub & sinks -------------------------------------------------------------
@pytest.mark.asyncio
async def test_hub_buffers_flushes_and_respects_opt_out():
    hub = TelemetryHub(settings(), sinks=[])
    repo = hub.memory_repo()
    await repo.set_opt_out("quiet", True)
    assert await hub.record(UsageEvent(name="feature_used", feature="ideas", creator_id="loud"))
    assert not await hub.record(UsageEvent(name="feature_used", feature="ideas", creator_id="quiet"))
    assert hub.stats["dropped_opt_out"] == 1 and len(repo.events) == 0
    assert await hub.flush() == 1 and len(repo.events) == 1
    # opt-out cache is invalidated when preferences change
    await repo.set_opt_out("quiet", False); hub.invalidate_opt_out("quiet")
    assert await hub.record(UsageEvent(name="feature_used", feature="ideas", creator_id="quiet"))


@pytest.mark.asyncio
async def test_hub_auto_flushes_when_buffer_full():
    hub = TelemetryHub(settings(telemetry_max_buffer=3), sinks=[])
    for i in range(3):
        await hub.record(UsageEvent(name="feature_used", feature="ideas", creator_id="c"))
    assert len(hub.memory_repo().events) == 3 and hub.stats["flushed"] == 3


@pytest.mark.asyncio
async def test_log_sink_emits_json_lines(caplog):
    caplog.set_level(logging.INFO, logger="datadive.telemetry")
    await LogSink().emit([UsageEvent(name="page_view", feature="board", creator_id="c").export("s")])
    line = json.loads(caplog.records[-1].getMessage())
    assert line["feature"] == "board" and line["source"] == "data-dive" and "creator_id" not in line


@pytest.mark.asyncio
async def test_webhook_sink_posts_batches_and_failures_are_contained():
    received = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["auth"] = request.headers.get("authorization")
        received["body"] = json.loads(request.content)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), headers={"Authorization": "Bearer tok"})
    sink = WebhookSink("https://collector.example/ingest", client=client)
    hub = TelemetryHub(settings(), sinks=[sink])
    await hub.record(UsageEvent(name="feature_used", feature="ideas", creator_id="c", action="generate"))
    await hub.flush()
    assert received["auth"] == "Bearer tok"
    assert received["body"]["source"] == "data-dive" and received["body"]["events"][0]["action"] == "generate"

    failing = WebhookSink("https://down.example", client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503))))
    hub2 = TelemetryHub(settings(), sinks=[failing])
    await hub2.record(UsageEvent(name="feature_used", feature="ideas", creator_id="c"))
    assert await hub2.flush() == 1 and hub2.stats["sink_errors"] == 1  # still persisted, no exception


@pytest.mark.asyncio
async def test_otlp_sink_builds_when_sdk_available():
    pytest.importorskip("opentelemetry.sdk")
    from app.services.telemetry.sinks import OtlpSink
    sink = OtlpSink("http://127.0.0.1:1/v1/logs", "x-api-key=abc")
    await sink.emit([UsageEvent(name="feature_used", feature="ideas", creator_id="c", properties={"n": 3}).export("s")])
    await sink.close()  # exporter failure is swallowed by the batch processor; nothing raises


# ---- feedback & prompts -------------------------------------------------------
def svc(repo=None, **kw):
    hub = TelemetryHub(settings(**kw), sinks=[])
    repo = repo or hub.memory_repo()
    return TelemetryService(repo, hub, "c1", settings=settings(**kw), now=NOW)


@pytest.mark.asyncio
async def test_prompt_frequency_rules():
    s = svc(feedback_min_uses=2)
    assert (await s.should_prompt("ideas", "generate"))["reason"] == "too_few_uses"
    for _ in range(2):
        await s.hub.record(UsageEvent(name="feature_used", feature="ideas", creator_id="c1", action="generate", ts=NOW))
    assert (await s.should_prompt("ideas", "random_action"))["reason"] == "not_a_feedback_moment"
    r = await s.should_prompt("ideas", "generate")
    assert r["prompt"] is True and [q["id"] for q in r["questions"]] == ["rating", "worth_it", "improvement"]
    # prompted today → daily cap for another feature, dismiss → cooldown for this one
    for _ in range(3):
        await s.hub.record(UsageEvent(name="feature_used", feature="board", creator_id="c1", action="move", ts=NOW))
    assert (await s.should_prompt("board", "move"))["reason"] == "daily_cap"
    await s.dismiss_prompt("ideas")
    s.now = NOW + timedelta(days=2)
    assert (await s.should_prompt("ideas", "generate"))["reason"] == "recently_dismissed"
    s.now = NOW + timedelta(days=8)
    assert (await s.should_prompt("ideas", "generate"))["prompt"] is True
    await s.submit_feedback({"feature": "ideas", "rating": 5, "worth_it": "yes"})
    s.now = NOW + timedelta(days=20)
    assert (await s.should_prompt("ideas", "generate"))["reason"] == "recent_feedback"
    s.now = NOW + timedelta(days=40)
    assert (await s.should_prompt("ideas", "generate"))["prompt"] is True
    assert (await s.should_prompt("nope"))["reason"] == "unknown_feature"


@pytest.mark.asyncio
async def test_submit_feedback_validates_and_emits_sentiment_event():
    s = svc()
    fb = await s.submit_feedback({"feature": "review", "rating": 2, "worth_it": "no", "improvement": "  too slow " * 200,
                                  "context": {"verdict": "underperformed", "secret": {"x": 1}}, "trigger": "prompt"})
    assert len(fb.improvement) == 1000 and fb.context == {"verdict": "underperformed"}
    await s.hub.flush()
    ev = [e for e in s.repo.events if e.name == "feedback_submitted"][0]
    assert ev.properties == {"rating": 2, "worth_it": "no", "has_comment": True} and "improvement" not in ev.properties
    with pytest.raises(InvalidEvent):
        await s.submit_feedback({"feature": "review", "rating": 9, "worth_it": "yes"})
    with pytest.raises(InvalidEvent):
        await s.submit_feedback({"feature": "review", "rating": 3, "worth_it": "maybe"})


# ---- summary ----------------------------------------------------------------
def test_summarize_funnel_features_and_feedback():
    def ev(feature, action, **kw):
        return UsageEvent(name=kw.pop("name", "feature_used"), feature=feature, creator_id="c1", action=action,
                          session_id=kw.pop("session", "s1"), ts=NOW - timedelta(days=kw.pop("ago", 0)), **kw)
    events = [ev("ideas", "generate"), ev("ideas", "generate", session="s2"), ev("ideas", "to_board"),
              ev("board", "published"), ev("board", "move", name="api_call", duration_ms=50, status=200),
              ev("board", "move", name="api_call", duration_ms=900, status=500),
              ev("analytics", None, name="page_view", duration_ms=30000), ev("ideas", "generate", ago=60)]
    fb = [FeatureFeedback("c1", "ideas", 4, "yes", "more", created_at=NOW),
          FeatureFeedback("c1", "ideas", 2, "somewhat", "", created_at=NOW),
          FeatureFeedback("c1", "board", 5, "yes", "love it", created_at=NOW - timedelta(days=90))]
    s = summarize(events, fb, days=30, now=NOW)
    assert s["totals"]["events"] == 7 and s["totals"]["sessions"] == 2
    assert [f["count"] for f in s["funnel"]] == [2, 1, 1, 0]
    assert s["funnel"][1]["conversion"] == 0.5
    assert s["most_used"] == "ideas"
    board = next(f for f in s["features"] if f["feature"] == "board")
    assert board["error_rate"] == 0.5 and board["p95_latency_ms"] == 900
    analytics = next(f for f in s["features"] if f["feature"] == "analytics")
    assert analytics["time_on_page_s"] == 30
    assert s["feedback"][0]["avg_rating"] == 3.0 and s["feedback"][0]["worth_score"] == 0.75
    assert len(s["comments"]) == 1 and s["totals"]["feedback_responses"] == 2


# ---- API ---------------------------------------------------------------------
def test_api_ingest_middleware_prompt_and_summary(client):
    h = {"X-Session-Id": "sess-A"}
    client.post("/api/ideas/generate", json={"count": 2}, headers=h)
    r = client.post("/api/telemetry/events", headers=h, json={"events": [
        {"name": "page_view", "feature": "ideas", "page": "/ideas", "session_id": "sess-A", "duration_ms": 4000},
        {"feature": "ideas", "action": "generate", "session_id": "sess-A"},
        {"feature": "ideas", "action": "generate", "session_id": "sess-A"},
        {"name": "nonsense", "feature": "ideas"},
    ]})
    assert r.status_code == 202 and r.json() == {"accepted": 3, "rejected": 1, "dropped": 0}
    assert client.get("/api/telemetry/features").json()["features"][0]["id"] == "dashboard"

    p = client.get("/api/feedback/prompt?feature=ideas&moment=generate").json()
    assert p["prompt"] is True and p["uses"] >= 3
    assert client.post("/api/feedback/prompt/ideas/dismiss").status_code == 204
    assert client.post("/api/feedback", json={"feature": "ideas", "rating": 1, "worth_it": "nah"}).status_code == 422
    fb = client.post("/api/feedback", json={"feature": "ideas", "rating": 4, "worth_it": "yes", "improvement": "Carousel ideas", "trigger": "prompt"})
    assert fb.status_code == 201 and fb.json()["trigger"] == "prompt"

    s = client.get("/api/telemetry/summary?days=7").json()
    assert s["scope"] == "me" and s["totals"]["feedback_responses"] == 1
    ideas = next(f for f in s["features"] if f["feature"] == "ideas")
    assert ideas["uses"] >= 3 and ideas["avg_latency_ms"] is not None  # middleware recorded the API call
    assert s["funnel"][0]["count"] >= 3 and s["comments"][0]["improvement"] == "Carousel ideas"
    # middleware never records the telemetry endpoints themselves or health
    assert all(f["feature"] not in ("usage", "feedback") or f["uses"] == 0 for f in s["features"])

    assert client.patch("/api/telemetry/preferences", json={"telemetry_opt_out": True}).json()["telemetry_opt_out"] is True
    before = client.get("/api/telemetry/summary?days=7").json()["totals"]["events"]
    client.get("/api/analytics/overview")
    client.post("/api/telemetry/events", json={"events": [{"feature": "board", "action": "move"}]})
    assert client.get("/api/telemetry/summary?days=7").json()["totals"]["events"] == before
    client.patch("/api/telemetry/preferences", json={"telemetry_opt_out": False})


def test_summary_scope_all_requires_admin(client, monkeypatch):
    from app.config import get_settings
    assert client.get("/api/telemetry/summary?scope=all").status_code == 200  # mock mode without admins → allowed
    monkeypatch.setenv("ADMIN_USER_IDS", "someone-else")
    get_settings.cache_clear()
    try:
        assert client.get("/api/telemetry/summary?scope=all").status_code == 403
        monkeypatch.setenv("ADMIN_USER_IDS", "00000000-0000-0000-0000-000000000001")  # the mock user
        get_settings.cache_clear()
        assert client.get("/api/telemetry/summary?scope=all").json()["scope"] == "all"
    finally:
        monkeypatch.delenv("ADMIN_USER_IDS")
        get_settings.cache_clear()
