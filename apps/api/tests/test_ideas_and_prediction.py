from app.services.analytics.ideas import IdeaGenerator, build_outline
from app.services.analytics.prediction import predict


def test_prediction_is_multiplicative_and_explainable(analysis):
    slot = analysis.best_slots("YouTube", 1)[0]
    p = predict(analysis, "YouTube", "Long-form", ["edit"], slot)
    f = p.factors
    expected = f["format_baseline_views"] * f["topic_lift"] * f["time_lift"] * f["calibration"]
    assert abs(p.expected_views - expected) / expected < 0.01
    assert p.views_low < p.expected_views < p.views_high
    assert 0.1 <= p.confidence <= 0.95
    assert p.expected_engagement_rate > 0


def test_calibration_scales_prediction(analysis):
    base = predict(analysis, "Instagram", "Reel", [], None)
    cal = predict(analysis, "Instagram", "Reel", [], None, calibration_factor=0.5, calibration_samples=3)
    assert abs(cal.expected_views - base.expected_views * 0.5) <= 1
    assert cal.confidence > base.confidence  # reviewed predictions raise confidence


def test_unknown_topic_has_neutral_lift(analysis):
    p = predict(analysis, "YouTube", "Long-form", ["zzz-not-a-topic"], None)
    assert p.factors["topic_lift"] == 1.0 and p.factors["topic_samples"] == 0


def test_generator_is_deterministic_and_diverse(analysis):
    a = IdeaGenerator(analysis, seed=0).generate(6)
    b = IdeaGenerator(analysis, seed=0).generate(6)
    assert [i.title for i in a] == [i.title for i in b]
    assert len({i.title for i in a}) == 6
    assert len({(i.platform, i.content_type, tuple(i.topics)) for i in a}) == 6
    strategies = {i.strategy for i in a}
    assert {"double_down", "cross_post", "series", "evergreen"} <= strategies
    for i in a:
        assert i.hook and len(i.outline) >= 4
        assert i.prediction["expected_views"] > 0
        assert i.platform in ("YouTube", "Instagram")
        assert i.rationale


def test_different_seed_gives_different_batch(analysis):
    a = IdeaGenerator(analysis, seed=0).generate(6)
    b = IdeaGenerator(analysis, seed=1).generate(6)
    assert [i.title for i in a] != [i.title for i in b]


def test_outline_depends_on_format():
    assert "0–3s" in build_outline("Reel", "editing", "fast", 3)[0]
    assert "Cold open" in build_outline("Long-form", "editing", "system", 3)[0]
    assert "Slide 1" in build_outline("Post", "editing", "beginner", 3)[0]


def test_generator_with_no_recurring_topics():
    from datetime import datetime, timezone
    from app.services.analytics.engine import Analysis
    from app.services.analytics.records import PostRecord
    posts = [PostRecord(id="1", platform="YouTube", content_type="Long-form", title="alpha",
                        published_at=datetime(2026, 9, 1, tzinfo=timezone.utc), views=100)]
    ideas = IdeaGenerator(Analysis(posts)).generate(6)
    assert ideas and all(i.prediction["expected_views"] >= 1 for i in ideas)
