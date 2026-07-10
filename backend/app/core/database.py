from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global engine
    if engine is None:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
    return SessionLocal


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_sessionmaker()() as session:
        yield session
