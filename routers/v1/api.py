"""routers/v1/api.py — v1 版本 API 路由总入口。"""

from fastapi import APIRouter

from routers.v1.projects import router as projects_router
from routers.v1.uml import router as uml_router

api_router = APIRouter()

# 项目管理路由（/projects）
api_router.include_router(projects_router, prefix="/projects", tags=["Projects"])

# UML 业务路由（/uml/{type}/extract, /uml/{type}/generate, /uml/sync）
api_router.include_router(uml_router, tags=["UML"])
