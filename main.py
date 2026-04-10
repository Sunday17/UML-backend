"""This file contains the main application entry point."""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel

# 导入 API 路由
from routers.v1.api import api_router
from core.config import settings
from core.logging import logger
from core.middleware import LoggingContextMiddleware

# UML 模型，用于 SQLAlchemy 自动建表
from models.uml import Project, UMLModel
from models.database import engine 

# Load environment variables
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    logger.info(
        "application_startup",
        project_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        api_prefix=settings.API_V1_STR or "none",
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
    openapi_url="/openapi.json",
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
app.include_router(api_router)