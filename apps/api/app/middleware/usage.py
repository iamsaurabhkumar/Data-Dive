"""
Records every authenticated API call as an `api_call` usage event.

* Uses the *route template* (e.g. /api/kanban/cards/{card_id}/move) — never raw ids.
* Never raises; never adds measurable latency (events are buffered, flushed in background).
* Skips health/docs/telemetry endpoints and unauthenticated requests.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.routing import Match

from app.config import get_settings
from app.dependencies import MOCK_USER
from app.services.telemetry.models import UsageEvent
from app.services.telemetry.service import get_hub
from app.services.telemetry.taxonomy import feature_for_route

logger = logging.getLogger("datadive.telemetry.middleware")

SKIP_PREFIXES = ("/api/health", "/api/telemetry", "/api/feedback", "/docs", "/openapi.json", "/redoc")

# Route template → action label (for the funnel); otherwise derived from the last path segment
ACTIONS = {
    ("POST", "/api/ideas/generate"): "generate",
    ("POST", "/api/projects/next"): "generate",
    ("POST", "/api/ideas/{idea_id}/to-board"): "to_board",
    ("POST", "/api/ideas/{idea_id}/dismiss"): "dismiss",
    ("POST", "/api/kanban/cards"): "create",
    ("POST", "/api/kanban/cards/{card_id}/move"): "move",
    ("POST", "/api/kanban/cards/{card_id}/link-post"): "link_post",
    ("POST", "/api/kanban/cards/{card_id}/review"): "review",
    ("DELETE", "/api/kanban/cards/{card_id}"): "delete",
    ("PATCH", "/api/kanban/cards/{card_id}"): "edit",
    ("POST", "/api/content/sync"): "sync",
    ("GET", "/api/analytics/patterns"): "view",
    ("GET", "/api/analytics/overview"): "view",
    ("GET", "/api/analytics/learning"): "view",
}


def user_id_from_request(request: Request) -> Optional[str]:
    settings = get_settings()
    if settings.mock_mode:
        return MOCK_USER["sub"]
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer ") or not settings.supabase_jwt_secret:
        return None
    try:
        payload = jwt.decode(auth[7:], settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
        return payload.get("sub")
    except JWTError:
        return None


def route_template(request: Request) -> Optional[str]:
    for route in request.app.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return getattr(route, "path", None)
    return None


class UsageTrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        try:
            await self._record(request, response.status_code, int((time.perf_counter() - start) * 1000))
        except Exception:  # pragma: no cover - defensive
            logger.exception("usage middleware failed")
        return response

    async def _record(self, request: Request, status: int, duration_ms: int) -> None:
        path = request.url.path
        if not path.startswith("/api/") or path.startswith(SKIP_PREFIXES) or request.method == "OPTIONS":
            return
        user_id = user_id_from_request(request)
        if not user_id:
            return
        template = route_template(request) or path
        action = ACTIONS.get((request.method, template))
        if action is None:
            action = "view" if request.method == "GET" else template.rstrip("/").split("/")[-1].strip("{}")
        props = {"method": request.method, "route": template}
        # Request bodies are not re-read here, so body-dependent steps (e.g. a move *to published*)
        # are emitted by the frontend as feature_used(board, published).
        await get_hub().record(UsageEvent(
            name="api_call", feature=feature_for_route(template), creator_id=user_id, action=action,
            properties=props, page=None, session_id=request.headers.get("x-session-id"), client="api",
            duration_ms=duration_ms, status=status,
        ))
