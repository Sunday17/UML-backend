"""This file contains the main application entry point."""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel

# 导入 API 路由
from api.v1.api import api_router
from core.config import settings
from core.logging import logger
from core.middleware import LoggingContextMiddleware
from services.database import database_service

# 【重点新增】：必须导入你的 UML 模型，SQLAlchemy 才能识别并建表
from app.models.uml import Project, UMLModel 
# 导入异步数据库引擎
from app.models.database import engine 

# Load environment variables
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    logger.info(
        "application_startup",
        project_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        api_prefix=settings.API_V1_STR,
    )
    
    # 【重点新增】：项目启动时，自动在 MySQL 中建表
    try:
        async with engine.begin() as conn:
            # 运行同步的建表语句
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("Database tables verified/created successfully.")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")

    yield
    
    logger.info("application_shutdown")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="UML Auto Generation System API",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Add logging context middleware
app.add_middleware(LoggingContextMiddleware)

# Add validation exception handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(
        "validation_error",
        path=request.url.path,
        errors=str(exc.errors()),
    )
    formatted_errors = [{"field": " -> ".join([str(loc) for loc in err["loc"] if loc != "body"]), "message": err["msg"]} for err in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": formatted_errors},
    )

# Set up CORS middleware (允许前端 Vue 跨域请求)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 毕设开发阶段建议设为 "*" 允许所有跨域
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    """Root endpoint returning basic API information."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "healthy",
        "swagger_url": "/docs",
    }

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    db_healthy = await database_service.health_check()
    status_code = status.HTTP_200_OK if db_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if db_healthy else "degraded",
            "components": {"api": "healthy", "database": "healthy" if db_healthy else "unhealthy"},
            "timestamp": datetime.now().isoformat(),
        }
    )