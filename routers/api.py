# routers/api.py
from fastapi import APIRouter

from routers.uml import router as uml_router
from core.logging import logger

api_router = APIRouter()

# UML 路由挂载（/uml 前缀已在 uml.py 中定义）
api_router.include_router(uml_router, tags=["UML"])


@api_router.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.info("health_check_called")
    return {"status": "healthy", "version": "1.0.0"}