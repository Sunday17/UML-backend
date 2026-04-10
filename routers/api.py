# app/routers/v1/api.py
from fastapi import APIRouter

# 【重点】导入你刚刚写好的 uml 路由
from app.routers.v1.uml import router as uml_router

from app.core.logging import logger

api_router = APIRouter()

# 【重点】挂载 UML 路由 (接口路径将变为 /uml/usecase/...)
api_router.include_router(uml_router, prefix="/uml", tags=["UML Auto Generation"])


@api_router.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.info("health_check_called")
    return {"status": "healthy", "version": "1.0.0"}