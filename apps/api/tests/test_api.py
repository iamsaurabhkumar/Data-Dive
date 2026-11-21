"""End-to-end tests of the Phase 3 API in mock mode (no DB, no Redis)."""


def test_health_boots_without_db_or_redis(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["mock_mode"] is True


def test_feed_is_stable_and_summary_consistent(client):
    a = client.get("/api/content/feed?sort_by=views").json()
    b = client.get("/api/content/feed?sort_by=views").json()
    assert a == b and a["total"] == 60
    s = client.get("/api/content/summary").json()
    assert s["total_posts"] == 60
    assert s["platform_breakdown"]["youtube"]["posts"] + s["platform_breakdown"]["instagram"]["posts"] == 60


def test_analytics_endpoints(client):
    ov = client.get("/api/analytics/overview").json()
    assert ov["total_posts"] == 60 and len(ov["platforms"]) == 2
    pat = client.get("/api/analytics/patterns").json()
    assert pat["sample_size"] == 60 and pat["topics"] and pat["formats"] and pat["findings"]
    assert set(pat["best_slots"]) == {"YouTube", "Instagram"}
    learn = client.get("/api/analytics/learning").json()
    assert learn["accuracy"]["count"] >= 1 and learn["calibrations"]


def test_seeded_board(client):
    board = client.get("/api/kanban/board").json()
    stages = {c["stage"]: len(c["cards"]) for c in board["columns"]}
    assert list(stages) == ["idea", "scripting", "filming", "editing", "published"]
    assert board["stages"] == ["idea", "scripting", "filming", "editing", "published"]
    published_col = next(c for c in board["columns"] if c["stage"] == "published")["cards"]
    assert [c["stage"] for c in published_col] == ["published", "reviewed"]  # reviewed lives inside Published
    reviewed = published_col[-1]
    assert reviewed["review"]["verdict"] in ("outperformed", "on_target", "underperformed")
    assert reviewed["linked_post"]


def test_full_idea_to_review_loop(client):
    gen = client.post("/api/ideas/generate", json={"count": 3, "seed": 11})
    assert gen.status_code == 201 and gen.json()["total"] == 3
    idea = gen.json()["ideas"][0]
    assert idea["hook"] and idea["outline"] and idea["prediction"]["expected_views"] > 0

    card = client.post(f"/api/ideas/{idea['id']}/to-board").json()
    assert card["stage"] == "idea" and card["suggestion_id"] == idea["id"]
    # idempotent: converting again returns the same card
    assert client.post(f"/api/ideas/{idea['id']}/to-board").json()["id"] == card["id"]
    assert client.get("/api/ideas?status=converted_to_kanban").json()["total"] >= 1

    cid = card["id"]
    assert client.post(f"/api/kanban/cards/{cid}/move", json={"stage": "scripting"}).json()["stage"] == "scripting"
    assert client.post(f"/api/kanban/cards/{cid}/move", json={"stage": "filming"}).json()["stage"] == "filming"
    # legacy stage names from old clients are mapped onto the new pipeline
    assert client.post(f"/api/kanban/cards/{cid}/move", json={"stage": "planning"}).json()["stage"] == "scripting"
    assert client.post(f"/api/kanban/cards/{cid}/move", json={"stage": "reviewed"}).status_code == 409
    assert client.post(f"/api/kanban/cards/{cid}/move", json={"stage": "nope"}).status_code == 409
    sched = client.post(f"/api/kanban/cards/{cid}/move", json={"stage": "editing"}).json()
    assert sched["scheduled_for"]  # publishing slot pencilled in from the recommended slot
    assert client.post(f"/api/kanban/cards/{cid}/review").status_code == 409

    pub = client.post(f"/api/kanban/cards/{cid}/move", json={"stage": "published"}).json()
    assert pub["published_at"]
    feed = client.get(f"/api/content/feed?platform={card['platform']}&content_type={card['content_type']}").json()["posts"]
    linked = client.post(f"/api/kanban/cards/{cid}/link-post", json={"post_id": feed[0]["id"]}).json()
    assert linked["post_id"] == feed[0]["id"] and linked["linked_post"]["title"] == feed[0]["title"]

    before = client.get("/api/analytics/learning").json()["accuracy"]["count"]
    reviewed = client.post(f"/api/kanban/cards/{cid}/review").json()
    assert reviewed["stage"] == "reviewed"
    rv = reviewed["review"]
    assert rv["verdict"] in ("outperformed", "on_target", "underperformed")
    assert rv["predicted"]["views"] == idea["prediction"]["expected_views"]
    assert rv["actual"]["views"] == feed[0]["metrics"]["views"]
    assert len(rv["lessons"]) >= 2
    after = client.get("/api/analytics/learning").json()
    assert after["accuracy"]["count"] == before + 1
    cal = next(c for c in after["calibrations"] if c["platform"] == card["platform"] and c["content_type"] == card["content_type"])
    assert cal["samples"] >= 1

    events = client.get(f"/api/kanban/cards/{cid}").json()["events"]
    assert [e["to_stage"] for e in events][-1] == "reviewed"
    assert client.get(f"/api/kanban/cards/{cid}/review").status_code == 200

    # reviewed is final
    assert client.post(f"/api/kanban/cards/{cid}/move", json={"stage": "idea"}).status_code == 409
    assert client.delete(f"/api/kanban/cards/{cid}").status_code == 204
    assert client.get(f"/api/kanban/cards/{cid}").status_code == 404


def test_manual_card_and_edit_reprices_forecast(client):
    c = client.post("/api/kanban/cards", json={"title": "Manual idea", "platform": "Instagram", "topics": ["camera"]})
    assert c.status_code == 201
    card = c.json()
    assert card["content_type"] in ("Reel", "Post") and card["prediction"]["expected_views"] > 0
    edited = client.patch(f"/api/kanban/cards/{card['id']}", json={"content_type": "Post", "notes": "hi"}).json()
    assert edited["content_type"] == "Post" and edited["notes"] == "hi"
    assert edited["prediction"]["content_type"] == "Post"
    assert client.post("/api/kanban/cards", json={"title": "x", "stage": "reviewed"}).status_code == 409


def test_auto_link_and_dismiss(client):
    feed = client.get("/api/content/feed?platform=YouTube&content_type=Long-form").json()["posts"]
    target = feed[3]
    card = client.post("/api/kanban/cards", json={"title": target["title"], "platform": "YouTube",
                                                  "content_type": "Long-form"}).json()
    client.post(f"/api/kanban/cards/{card['id']}/move", json={"stage": "published"})
    client.patch(f"/api/kanban/cards/{card['id']}", json={"published_at": target["published_at"]})
    linked = client.post(f"/api/kanban/cards/{card['id']}/link-post", json={"auto": True}).json()
    assert linked["post_id"] == target["id"]

    ideas = client.get("/api/ideas").json()["ideas"]
    d = client.post(f"/api/ideas/{ideas[0]['id']}/dismiss").json()
    assert d["status"] == "rejected"
    assert client.post("/api/ideas/does-not-exist/dismiss").status_code == 404


def test_auth_is_enforced_outside_mock_mode(monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    from jose import jwt
    from app.config import get_settings
    from app.dependencies import get_current_user

    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "real-secret")
    get_settings.cache_clear()
    try:
        forged = jwt.encode({"sub": "victim", "aud": "authenticated"}, "ATTACKER", algorithm="HS256")
        try:
            asyncio.run(get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=forged)))
            assert False, "forged token accepted"
        except HTTPException as exc:
            assert exc.status_code == 401
        good = jwt.encode({"sub": "me", "aud": "authenticated"}, "real-secret", algorithm="HS256")
        payload = asyncio.run(get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=good)))
        assert payload["sub"] == "me"
        try:
            asyncio.run(get_current_user(None))
            assert False
        except HTTPException as exc:
            assert exc.status_code == 401
    finally:
        get_settings.cache_clear()


def test_insights_detail_matches_headline_platform(client):
    ww = client.get("/api/metrics/insights").json()["what_works"]
    other = "YouTube" if ww["top_platform"] == "Instagram" else "Instagram"
    assert other not in ww["recommendation_text"].split(".", 1)[1]
