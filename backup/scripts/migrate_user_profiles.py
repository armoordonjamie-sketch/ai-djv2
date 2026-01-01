"""Migration script to create user_profiles table.

Run with: python -m backend_v2.scripts.migrate_user_profiles
"""
import asyncio
import logging
from sqlalchemy import text

from backend_v2.db.session import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Create user_profiles table."""
    
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id VARCHAR(36) PRIMARY KEY,
        display_name VARCHAR(100),
        age_range VARCHAR(20),
        location VARCHAR(200),
        occupation VARCHAR(100),
        favorite_genres TEXT,
        favorite_artists TEXT,
        favorite_songs TEXT,
        no_go TEXT,
        explicit_lyrics VARCHAR(20) DEFAULT 'ok',
        dj_personality VARCHAR(30) DEFAULT 'casual_funny',
        raw_context TEXT,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """
    
    async with engine.begin() as conn:
        # Create table
        logger.info("Creating user_profiles table...")
        await conn.execute(text(create_table_sql))
        logger.info("✅ user_profiles table created")
        
        # Create index on user_id (already PK, but explicit)
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_user_profiles_user_id ON user_profiles(user_id)"
            ))
        except Exception:
            pass  # Index may already exist
        
        logger.info("✅ Migration complete")


if __name__ == "__main__":
    asyncio.run(migrate())
