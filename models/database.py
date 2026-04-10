# models/database.py
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

# Settings must be imported after dotenv is loaded (main.py does load_dotenv first)
from core.config import settings

engine = create_async_engine(
    str(settings.DATABASE_URL),
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
)


async def get_session() -> AsyncSession:
    """提供给 FastAPI Depends 使用的异步会话生成器"""
    async_session = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session() as session:
        yield session