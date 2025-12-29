"""Async SQLAlchemy engine and session factory.

IMPORTANT: SQLite foreign key enforcement is enabled via PRAGMA foreign_keys=ON
on each connection. This ensures referential integrity.
"""
import logging
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)

from backend_v2.config import DATABASE_URL

logger = logging.getLogger("ai-dj.db")


# Create async engine
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL debugging
    pool_pre_ping=True,  # Test connections before use
)


# Enable SQLite foreign key enforcement on each connection
# This is critical for data integrity!
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key constraints and optimization for SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")  # 30 seconds
    cursor.close()
    logger.debug("SQLite WAL enabled with 30s busy_timeout")


# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that yields an async database session.
    
    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_async_session)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions outside FastAPI request context.
    
    Usage:
        async with get_db_session() as db:
            result = await db.execute(select(Item))
            items = result.scalars().all()
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()




async def init_db():
    """
    Initialize database (create tables).
    
    NOTE: In production, use Alembic migrations instead of this function.
    This is provided for development convenience only.
    """
    from backend_v2.db.base import Base
    # Import all models to ensure they're registered with Base.metadata
    from backend_v2 import models  # noqa: F401
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database tables created (dev mode)")


async def close_db():
    """Close database engine and all connections."""
    await engine.dispose()
    logger.info("Database engine disposed")
