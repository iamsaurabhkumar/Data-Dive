from datetime import datetime, timedelta, timezone

from app.services.analytics.engine import Analysis, shrunk_geo_mean
from app.services.analytics.records import PostRecord, hour_bucket
from app.services.analytics.topics import extract_topics, stem, tokenize


def make(id_, platform, ct, title, views, days_ago=10, hour=9, likes=None, now=None):
    now = now or datetime(2026, 10, 1, tzinfo=timezone.utc)
    return PostRecord(id=id_, platform=platform, content_type=ct, title=title,
                      published_at=(now - timedelta(days=days_ago)).replace(hour=hour),
                      views=views, likes=likes if likes is not None else views // 20, comments=views // 200)


# ---- helpers -----------------------------------------------------------
def test_hour_buckets():
    assert hour_bucket(6) == "morning" and hour_bucket(11) == "morning"
    assert hour_bucket(12) == "midday" and hour_bucket(17) == "evening"
    assert hour_bucket(22) == "night" and hour_bucket(3) == "night"


def test_shrinkage_pulls_small_samples_towards_one():
    assert shrunk_geo_mean([3.0]) < 3.0
    assert abs(shrunk_geo_mean([1.0, 1.0, 1.0]) - 1.0) < 1e-9
    big = shrunk_geo_mean([2.0] * 50)
    assert 1.9 < big <= 2.0
    assert shrunk_geo_mean([100.0] * 50) == 3.0  # capped


def test_tokenize_and_stem():
    assert stem("editing") == "edit" and stem("cameras") == "camera"
    assert stem("settings") == stem("setting") == "set"
    assert stem("tried") == "try" and stem("news") == "news" and stem("tips") == "tip"
    toks = tokenize("How I Edit Videos 10x Faster — Workflow Secrets (I've tried)")
    assert "edit" in toks and "workflow" in toks
    assert "i've" not in toks and "videos" not in toks and "how" not in toks


def test_extract_topics_requires_recurrence():
    titles = ["Desk setup tour", "My desk setup on a budget", "Unique one-off title"]
    topics, labels = extract_topics(titles, min_docs=2)
    assert "desk setup" in topics[0] and "desk setup" in topics[1]
    assert topics[2] == []
    assert labels.label("desk setup") == "desk setup"


def test_topic_labels_are_per_corpus():
    _, a = extract_topics(["Editing tips", "Editing hacks"])
    _, b = extract_topics(["Edit faster", "Edit smarter"])
    assert a.label("edit") == "editing" and b.label("edit") == "edit"


# ---- engine ------------------------------------------------------------
def test_relative_performance_is_format_normalized():
    posts = [
        make("a", "YouTube", "Short", "short one", 100_000),
        make("b", "YouTube", "Short", "short two", 300_000),
        make("c", "YouTube", "Long-form", "long one", 10_000),
        make("d", "YouTube", "Long-form", "long two", 30_000),
    ]
    a = Analysis(posts)
    # Each pair has the same relative performance despite 10x raw difference
    assert abs(a.rel["a"] - a.rel["c"]) < 1e-9
    assert abs(a.rel["b"] - a.rel["d"]) < 1e-9
    assert a.baseline_views("YouTube", "Short") == 200_000
    assert a.baseline_views("YouTube", "Long-form") == 20_000


def test_format_stats_compare_against_platform_median():
    posts = [make("a", "YouTube", "Short", "s", 100_000), make("b", "YouTube", "Short", "s2", 120_000),
             make("c", "YouTube", "Long-form", "l", 10_000), make("d", "YouTube", "Long-form", "l2", 12_000)]
    fmt = Analysis(posts).format_stats()
    assert fmt[0].key == "YouTube:Short" and fmt[0].lift > 1.0
    assert fmt[-1].key == "YouTube:Long-form" and fmt[-1].lift < 1.0


def test_topic_lift_detects_winning_topic():
    posts = [make(f"e{i}", "YouTube", "Long-form", f"Editing tips #{i}", 40_000) for i in range(4)]
    posts += [make(f"o{i}", "YouTube", "Long-form", f"Random vlog day {i}", 10_000) for i in range(4)]
    a = Analysis(posts)
    lift, n = a.topic_lift("edit")
    assert n == 4 and lift > 1.3
    lift_vlog, _ = a.topic_lift("vlog")
    assert lift_vlog < 0.8
    labels = [t.label for t in a.topic_stats()]
    assert labels[0] == "editing tips"  # "editing" alone is collapsed into the more specific bigram


def test_time_lift_and_best_slots():
    # Tuesday 9:00 posts perform 3x
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)  # Thursday
    tuesday = now - timedelta(days=2)
    posts = []
    for i in range(4):
        posts.append(PostRecord(id=f"t{i}", platform="YouTube", content_type="Long-form", title=f"tue {i}",
                                published_at=(tuesday - timedelta(days=7 * i)).replace(hour=9), views=30_000))
        posts.append(PostRecord(id=f"s{i}", platform="YouTube", content_type="Long-form", title=f"sun {i}",
                                published_at=(tuesday - timedelta(days=7 * i + 2)).replace(hour=22), views=10_000))
    a = Analysis(posts, now=now)
    assert a.time_lift(1, "morning") > 1.2
    assert a.time_lift(6, "night") < 0.8
    best = a.best_slots("YouTube", 1)[0]
    assert best["weekday_label"] == "Tue" and best["hour_bucket"] == "morning"


def test_overview_and_findings_on_mock_data(analysis):
    ov = analysis.overview()
    assert ov["total_posts"] == 60
    assert {p["platform"] for p in ov["platforms"]} == {"YouTube", "Instagram"}
    assert 0 < ov["avg_engagement_rate"] < 100
    pats = analysis.patterns()
    kinds = {f["kind"] for f in pats["findings"]}
    assert "format" in kinds and "topic" in kinds
    # Every reported topic has at least MIN_GROUP posts
    assert all(t["posts"] >= 2 for t in pats["topics"])
    assert all(0.4 <= t["lift"] <= 3.0 for t in pats["topics"])


def test_empty_history_is_safe():
    a = Analysis([])
    assert a.overview()["total_posts"] == 0
    assert a.patterns()["topics"] == []
    assert a.findings()[0].headline.startswith("Not enough data")
    assert a.baseline_views("YouTube", "Short") == 1.0


def test_redundant_topic_fragments_are_collapsed():
    posts = [make("a", "YouTube", "Long-form", "Desk setup tour", 10_000),
             make("b", "YouTube", "Long-form", "My desk setup on a budget", 12_000),
             make("c", "YouTube", "Long-form", "Budget lighting", 9_000)]
    keys = [t.key for t in Analysis(posts).topic_stats()]
    assert "desk setup" in keys and "desk" not in keys and "setup" not in keys
    assert "budget" in keys  # different member set than "desk setup" → kept


def test_topic_lift_accepts_display_labels():
    posts = [make(f"e{i}", "YouTube", "Long-form", f"Editing tips #{i}", 40_000) for i in range(3)]
    posts += [make(f"o{i}", "YouTube", "Long-form", f"Random vlog {i}", 10_000) for i in range(3)]
    a = Analysis(posts)
    assert a.topic_lift("Editing Tips") == a.topic_lift("edit tip")
    assert a.topic_lift("editing")[1] == 3
