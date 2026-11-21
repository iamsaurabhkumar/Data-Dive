"""
Stable feature taxonomy. Dashboards and exports key on these names, so
add new ones here rather than inventing strings in the UI.
"""
from __future__ import annotations

FEATURES = {
    "dashboard": "Dashboard (feed & KPIs)",
    "insights": "Insights (legacy)",
    "analytics": "Analytics (patterns & overview)",
    "ideas": "Idea generator",
    "board": "Production board",
    "review": "Prediction review & learning",
    "trend_feed": "Trend feed (worker suggestions)",
    "sync": "Platform sync",
    "feedback": "Feedback & surveys",
    "usage": "Usage dashboard",
    "next_project": "Generate Next Project",
    "auth": "Auth / profile",
    "other": "Other",
}

EVENT_NAMES = ("page_view", "feature_used", "api_call", "feedback_submitted", "survey_dismissed", "survey_shown")

# Route prefix → feature, used by the API middleware. Order matters (longest first).
ROUTE_FEATURES = [
    ("/api/kanban/cards/{card_id}/review", "review"),
    ("/api/kanban/cards/{card_id}/link-post", "review"),
    ("/api/kanban", "board"),
    ("/api/ideas", "ideas"),
    ("/api/projects", "next_project"),
    ("/api/analytics/learning", "review"),
    ("/api/analytics", "analytics"),
    ("/api/metrics", "insights"),
    ("/api/content/sync", "sync"),
    ("/api/content", "dashboard"),
    ("/api/auth", "auth"),
    ("/api/feedback", "feedback"),
    ("/api/telemetry", "usage"),
]

# Funnel steps: (label, feature, action) — counted from feature_used / api_call events
FUNNEL = [
    ("Ideas generated", "ideas", "generate"),
    ("Added to board", "ideas", "to_board"),
    ("Published", "board", "published"),
    ("Reviewed", "review", "review"),
]

# Feature "moments" after which it makes sense to ask for feedback
FEEDBACK_MOMENTS = {
    "ideas": ("generate", "to_board"),
    "board": ("move",),
    "review": ("review",),
    "analytics": ("view",),
    "next_project": ("generate", "to_board"),
}


def feature_for_route(route_template: str) -> str:
    for prefix, feature in ROUTE_FEATURES:
        if route_template.startswith(prefix):
            return feature
    return "other"
