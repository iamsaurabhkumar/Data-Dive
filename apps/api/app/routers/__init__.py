from app.routers.content import router as content_router
from app.routers.auth import router as auth_router
from app.routers.metrics import router as metrics_router
from app.routers.analytics import router as analytics_router
from app.routers.ideas import router as ideas_router
from app.routers.kanban import router as kanban_router

__all__ = ["content_router", "auth_router", "metrics_router", "analytics_router", "ideas_router", "kanban_router"]
