from fastapi import APIRouter

from app.api.routes.chat import router as chat_router
from app.api.routes.dashboard import router as dashboard_router

router = APIRouter(prefix="/api")


@router.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


router.include_router(dashboard_router)
router.include_router(chat_router)
