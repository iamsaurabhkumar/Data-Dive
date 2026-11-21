from datetime import datetime, timedelta, timezone

from app.services.analytics.learning import (
    Calibration, accuracy_summary, auto_match_post, review_prediction, update_calibration,
)
from app.services.analytics.prediction import predict
from app.services.analytics.records import PostRecord


def test_update_calibration_moves_towards_ratio_and_is_bounded():
    c = update_calibration(None, "u", "YouTube", "Short", 2.0)
    assert 1.0 < c.factor < 2.0 and c.samples == 1
    c2 = update_calibration(c, "u", "YouTube", "Short", 2.0)
    assert c2.factor > c.factor and c2.samples == 2
    for _ in range(50):
        c2 = update_calibration(c2, "u", "YouTube", "Short", 100.0)
    assert c2.factor == 4.0  # ceiling
    for _ in range(50):
        c2 = update_calibration(c2, "u", "YouTube", "Short", 0.0001)
    assert c2.factor == 0.25  # floor


def test_review_verdicts(analysis):
    slot = analysis.best_slots("YouTube", 1)[0]
    pred = predict(analysis, "YouTube", "Long-form", [], slot).to_dict()
    when = datetime(2026, 9, 20, 9, tzinfo=timezone.utc)

    over = PostRecord(id="x", platform="YouTube", content_type="Long-form", title="Editing tips", published_at=when,
                      views=pred["views_high"] * 2, likes=1000)
    res, cal = review_prediction(pred, over, analysis, None, "u", slot)
    assert res.verdict == "outperformed" and res.views_ratio > 1 and cal.factor > 1

    under = PostRecord(id="y", platform="YouTube", content_type="Long-form", title="Editing tips", published_at=when,
                       views=max(pred["views_low"] // 2, 1))
    res, cal = review_prediction(pred, under, analysis, None, "u", slot)
    assert res.verdict == "underperformed" and cal.factor < 1
    assert any("Missed the forecast" in l for l in res.lessons)
    assert any("Calibration" in l for l in res.lessons)

    on = PostRecord(id="z", platform="YouTube", content_type="Long-form", title="Editing tips", published_at=when,
                    views=pred["expected_views"])
    res, _ = review_prediction(pred, on, analysis, None, "u", slot)
    assert res.verdict == "on_target" and res.within_range


def test_review_mentions_timing_when_slot_differs(analysis):
    slot = {"weekday": 1, "hour_bucket": "morning", "lift": 1.3}
    pred = predict(analysis, "YouTube", "Long-form", [], slot).to_dict()
    sunday_night = datetime(2026, 9, 27, 23, tzinfo=timezone.utc)  # Sunday
    post = PostRecord(id="p", platform="YouTube", content_type="Long-form", title="t", published_at=sunday_night,
                      views=pred["expected_views"])
    res, _ = review_prediction(pred, post, analysis, None, "u", slot)
    assert any("instead of the recommended Tue morning" in l for l in res.lessons)


def test_accuracy_summary():
    assert accuracy_summary([])["count"] == 0
    reviews = [{"views_ratio": 2.0, "abs_pct_error": 1.0, "within_range": False},
               {"views_ratio": 0.5, "abs_pct_error": 0.5, "within_range": True},
               {"views_ratio": 1.1, "abs_pct_error": 0.1, "within_range": True},
               {"views_ratio": 0.9, "abs_pct_error": 0.1, "within_range": True}]
    s = accuracy_summary(reviews)
    assert s["count"] == 4 and s["hit_rate"] == 0.75
    assert abs(s["bias"] - 1.0) < 0.02   # 2.0 * 0.5 * 1.1 * 0.9 ≈ 1
    assert s["trend"] > 0                # errors shrank over time


def test_auto_match_post(posts):
    target = posts[5]
    m = auto_match_post(posts, target.title.upper() + " (final cut)", target.platform, target.content_type,
                        target.published_at + timedelta(days=1))
    assert m and m[0].id == target.id
    assert auto_match_post(posts, "completely unrelated zebra quantum", target.platform, None, None) is None
    # outside the date window
    assert auto_match_post(posts, target.title, target.platform, None, target.published_at + timedelta(days=60)) is None
