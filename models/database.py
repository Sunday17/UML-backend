# app/models/database.py
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from core.config import Settings
settings = Settings()

# 1. 创建异步数据库引擎 (针对 MySQL 进行优化)
engine = create_async_engine(
    str(settings.DATABASE_URL),
    echo=False,          # 生产环境设为 False，开发时可设为 True 打印 SQL 语句
    pool_pre_ping=True,  # 关键：每次连接前测试连通性，防止 MySQL 默认断开空闲连接
    pool_recycle=3600,   # 定期回收连接
)

# 2. 定义获取异步 Session 的依赖函数 (供 API 路由使用)
async def get_session() -> AsyncSession:
    """提供给 FastAPI Depends 使用的异步会话生成器"""
    async_session = sessionmaker(
        bind=engine, 
        class_=AsyncSession, 
        expire_on_commit=False
    )
    async with async_session() as session:
        yield session