"""Alembic environment configuration for async SQLAlchemy.

This env.py is configured for:
1. Async database operations (SQLite + aiosqlite)
2. Auto-detection of model changes via target_metadata
3. SQLite-compatible Alembic operations

MIGRATION WORKFLOW:
- For NEW installs: alembic upgrade head
- For EXISTING db (tables created by old db.py):
  1. alembic stamp head  # Mark current state as "up to date"
  2. alembic upgrade head  # Apply future migrations
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import config and models
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parents[2]
sys.path.insert(0, str(project_root))

from backend_v2.config import DATABASE_URL
from backend_v2.db.base import Base
# Import all models to ensure they're registered
from backend_v2 import models  # noqa: F401

# Alembic Config object
config = context.config

# Override sqlalchemy.url with environment variable
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    # Enable foreign keys for SQLite
    if connection.dialect.name == "sqlite":
        connection.execute(text("PRAGMA foreign_keys=ON"))
    
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
