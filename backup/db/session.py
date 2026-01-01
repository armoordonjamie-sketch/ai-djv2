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
# Following SQLAlchemy 2.0 async best practices:
# - pool_pre_ping: Validates connections before use (prevents stale connections)
# - echo: Set to False in production, True for SQL debugging
# - For SQLite: Uses aiosqlite driver (specified in DATABASE_URL)
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL debugging
    pool_pre_ping=True,  # Test connections before use (recommended for production)
    # pool_size and max_overflow are handled automatically by SQLAlchemy
    # For SQLite, connection pooling is minimal but still managed
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
    cursor.execute("PRAGMA busy_timeout=60000")  # 60 seconds - allows for concurrent background tasks
    cursor.close()
    logger.debug("SQLite WAL enabled with 60s busy_timeout")


# Create async session factory
# expire_on_commit=False: Prevents objects from expiring after commit,
# allowing access to attributes without triggering lazy loads
# autoflush=False: Gives explicit control over when to flush changes
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Recommended for async: prevents lazy load issues
    autoflush=False,  # Explicit flush control
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.
    
    Follows FastAPI and SQLAlchemy 2.0 async best practices:
    - Yields session for use in path operations
    - Rolls back on exceptions to maintain data integrity
    - Routes should explicitly commit successful transactions
    - Closes session in finally block to ensure cleanup
    
    Based on:
    - FastAPI: https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/
    - SQLAlchemy 2.0 async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
    
    Usage:
        @app.post("/items")
        async def create_item(item: Item, db: AsyncSession = Depends(get_async_session)):
            db.add(item)
            await db.commit()  # Explicit commit in route
            return item
    """
    async with async_session_factory() as session:
        try:
            yield session
            # Routes should explicitly commit successful transactions
            # We don't auto-commit here to give routes explicit control
        except Exception:
            # Rollback on any exception to maintain data integrity
            # This is critical: uncommitted changes must be rolled back
            await session.rollback()
            raise
        finally:
            # Always close the session to release connection back to pool
            # This is essential for connection pool management
            await session.close()


from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions outside FastAPI request context.
    
    Use this for background tasks, workers, or any code that needs a DB session
    but isn't running in a FastAPI dependency context.
    
    Following SQLAlchemy 2.0 async best practices:
    - Creates new session from factory
    - Rolls back on exceptions
    - Always closes session to release connection
    
    Based on FastAPI 0.106.0+ recommendation: background tasks should create
    their own resources rather than sharing dependencies.
    
    Usage:
        async with get_db_session() as db:
            result = await db.execute(select(Item))
            items = result.scalars().all()
            await db.commit()  # Explicit commit required
    """
    async with async_session_factory() as session:
        try:
            yield session
            # Note: Caller must explicitly commit successful transactions
        except Exception:
            # Rollback on any exception to maintain data integrity
            await session.rollback()
            raise
        finally:
            # Always close the session to release connection back to pool
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
