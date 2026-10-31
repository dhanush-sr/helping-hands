from fastapi import APIRouter

from app import __version__
from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check used by CI, the deploy pipeline and the frontend."""
    settings = get_settings()
    return {"status": "ok", "version": __version__, "environment": settings.environment}
