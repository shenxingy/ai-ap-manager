from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_readonly_session() -> AsyncGenerator[AsyncSession, None]:
    """Read-only session: sets transaction to READ ONLY mode.

    Used by endpoints that execute untrusted queries (e.g. ask_ai)
    to prevent any DML even if SQL validation is bypassed.
    """
    async with AsyncSessionLocal() as session:
        from sqlalchemy import text
        await session.execute(text("SET TRANSACTION READ ONLY"))
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
