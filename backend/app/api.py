"""Public API assembly; dependency exports remain compatible with existing clients/tests."""

from fastapi import APIRouter

from .routes import system, plugins, trends, ocr, contents, covers, style, analytics, comments
from .routes.dependencies import get_analytics_llm_provider, get_ocr_provider

__all__ = ["router", "get_analytics_llm_provider", "get_ocr_provider"]

router = APIRouter(prefix="/api")
router.include_router(system.router)
router.include_router(plugins.router)
router.include_router(trends.router)
router.include_router(ocr.router)
router.include_router(contents.router)
router.include_router(covers.router)
router.include_router(style.router)
router.include_router(analytics.router)
router.include_router(comments.router)
