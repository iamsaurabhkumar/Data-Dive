"""Generate Next Project: trend scoring, project building, fallback, API."""
from datetime import timedelta

from app.services.analytics.next_project import NextProjectGenerator, clean_subject, title_case
from app.services.analytics.prediction import predict
from app.services.analytics.trends import TrendRecord, mock_trends, score_trends
from app.services.mock_data import MOCK_NOW


def trend(id_, title, tags, vph=10_000, age_h=5, source="youtube"):
    return TrendRecord(id=id_, source=source, category="x", title=title, tags=tags,
                       fetched_at=MOCK_NOW - timedelta(hours=age_h), views=vph * 20, views_per_hour=vph)


def test_scoring_prefers_relevant_over_merely_viral(analysis):
    scored = score_trends(analysis, mock_trends(MOCK_NOW))
    top = scored[0]
    assert top.matched_topics and top.relevance > 0.3
    viral_offniche = next(s for s in scored if s.trend.id == "mt-08")   # cloud bread, highest velocity
    assert viral_offniche.momentum == 1.0 and viral_offniche.relevance < 0.1
    assert scored.index(viral_offniche) > 3
    assert all(0 <= s.score <= 1 for s in scored)


def test_scoring_excludes_and_drops_stale(analysis):
    ts = [trend("a", "Editing transitions hack", ["editing"]), trend("old", "Editing tips", ["editing"], age_h=24 * 9)]
    ids = [s.trend.id for s in score_trends(analysis, ts)]
    assert ids == ["a"]
    assert score_trends(analysis, ts, exclude_ids=["a"]) == []


def test_subject_cleaning_and_title_case():
    assert clean_subject("The 'invisible cut' transition everyone is copying") == "The 'invisible cut' transition"
    assert clean_subject("Analog desk setup trend — no screens") == "Analog desk setup"
    assert clean_subject("iPhone 17 Pro cinematic mode — camera test") == "iPhone 17 Pro cinematic mode"
    assert title_case("iPhone 17 pro for the win") == "iPhone 17 Pro for the Win"
    assert title_case("the 'invisible cut' with AI") == "The 'Invisible Cut' with AI"


def test_extra_lifts_are_bounded_and_reported(analysis):
    base = predict(analysis, "Instagram", "Reel", [], None)
    boosted = predict(analysis, "Instagram", "Reel", [], None, extra_lifts={"trend": 9.0})
    assert boosted.factors["extra_lifts"] == {"trend": 1.25}
    assert abs(boosted.expected_views - base.expected_views * 1.25) <= 1
    assert "extra_lifts" not in base.factors


def test_generator_builds_complete_trend_project(analysis):
    res = NextProjectGenerator(analysis, mock_trends(MOCK_NOW)).generate()
    idea = res.idea
    assert res.chosen and res.fallback_reason is None and idea.trend_id == res.chosen.trend.id
    assert idea.source == "trend" and idea.strategy == "trend_jack"
    assert idea.title and idea.hook and len(idea.outline) >= 5
    assert any("Trend context" in b or "Why now" in b for b in idea.outline)
    assert 1.0 <= idea.prediction["factors"]["extra_lifts"]["trend"] <= 1.2
    kit = idea.kit
    assert set(kit["checklist"]) == {"idea", "scripting", "filming", "editing", "published"}  # Kanban columns
    assert kit["shot_list"] and kit["thumbnail"]["text"] and kit["hashtags"] and kit["trend_window"]
    assert len(kit["hashtags"]) == len(set(kit["hashtags"]))
    assert res.alternatives and res.chosen not in res.alternatives


def test_generator_regenerate_and_platform_filter(analysis):
    g = NextProjectGenerator(analysis, mock_trends(MOCK_NOW))
    first = g.generate()
    second = g.generate(exclude_trend_ids=[first.idea.trend_id])
    assert second.idea.trend_id != first.idea.trend_id
    yt = g.generate(platform="YouTube")
    assert yt.idea.platform == "YouTube"


def test_fallbacks(analysis):
    none = NextProjectGenerator(analysis, []).generate()
    assert none.fallback_reason == "no_trends" and none.idea.trend_id is None
    assert none.idea.kit["checklist"] and none.idea.kit["trend_window"] is None
    assert none.idea.rationale.startswith("No fresh trends")
    offniche = NextProjectGenerator(analysis, [trend("f", "Cloud bread recipe", ["baking"], vph=99_000)]).generate()
    assert offniche.fallback_reason == "no_relevant_trends"
    assert offniche.alternatives[0].trend.id == "f"  # still shown, so the creator sees why


# ---- API (mock mode) -----------------------------------------------------------------
def test_api_next_project_flow(client):
    r = client.post("/api/projects/next", json={})
    assert r.status_code == 201
    d = r.json()
    assert d["enrichment"] == "disabled" and d["trend_refresh"] is None  # mock mode: no worker
    assert d["trend"]["matched_topics"] and d["trends_considered"] >= 6
    idea = d["idea"]
    assert idea["kit"]["checklist"]["filming"] and idea["trend_id"] == d["trend"]["trend"]["id"]

    polled = client.get(f"/api/ideas/{idea['id']}").json()
    assert polled["id"] == idea["id"] and polled["kit"] == idea["kit"]
    assert client.get("/api/ideas/nope").status_code == 404

    # regenerate: client excludes + server never repeats a trend already proposed
    again = client.post("/api/projects/next", json={"exclude_trend_ids": []}).json()
    assert again["trend"]["trend"]["id"] != d["trend"]["trend"]["id"]

    card = client.post(f"/api/ideas/{idea['id']}/to-board").json()
    assert card["stage"] == "idea" and "Shot list" in card["notes"] and "Filming:" in card["notes"]
    assert client.post("/api/projects/next", json={"platform": "TikTok"}).status_code == 422


def test_api_next_project_is_tracked(client):
    client.post("/api/projects/next", json={})
    s = client.get("/api/telemetry/summary?days=1").json()
    feat = next(f for f in s["features"] if f["feature"] == "next_project")
    assert feat["uses"] >= 1 and feat["top_actions"][0]["action"] == "generate"


def test_category_does_not_create_topic_matches(analysis):
    # "creator" is a topic for the mock creator; a trend merely *categorised* as creator must not match it
    t = TrendRecord(id="c", source="youtube", category="creator", title="Quantum zebra synthesis", tags=["zebra"],
                    fetched_at=MOCK_NOW, views=1, views_per_hour=1)
    assert score_trends(analysis, [t])[0].matched_topics == []


def test_mid_title_article_is_lowercased(analysis):
    titles = []
    for seed in range(8):
        res = NextProjectGenerator(analysis, mock_trends(MOCK_NOW), seed=seed).generate()
        titles.append(res.idea.title)
    assert not any(" The 'Invisible" in t for t in titles if not t.startswith("The"))
