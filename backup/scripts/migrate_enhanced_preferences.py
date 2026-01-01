"""Migration script to add enhanced preference columns to user_profiles.

Run with: python -m backend_v2.scripts.migrate_enhanced_preferences

This migration adds:
- energy_preference: User's energy preference (high_energy, low_energy, mixed)
- tempo_preference: User's tempo preference (fast, slow, mixed)
- listening_contexts: JSON array of contexts (workout, focus, party, etc.)
- era_preference: User's era preference (new_releases, classics, mixed)
"""
import asyncio
import logging
from sqlalchemy import text

from backend_v2.db.session import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Add enhanced preference columns to user_profiles table."""
    
    columns_to_add = [
        ("energy_preference", "VARCHAR(20) DEFAULT NULL"),
        ("tempo_preference", "VARCHAR(20) DEFAULT NULL"),
        ("listening_contexts", "TEXT DEFAULT NULL"),
        ("era_preference", "VARCHAR(20) DEFAULT 'mixed'"),
    ]
    
    async with engine.begin() as conn:
        for column_name, column_type in columns_to_add:
            try:
                logger.info(f"Adding column {column_name}...")
                await conn.execute(text(
                    f"ALTER TABLE user_profiles ADD COLUMN {column_name} {column_type}"
                ))
                logger.info(f"✅ Added {column_name}")
            except Exception as e:
                if "Duplicate column" in str(e) or "already exists" in str(e).lower():
                    logger.info(f"⏭️ Column {column_name} already exists, skipping")
                else:
                    logger.warning(f"⚠️ Could not add {column_name}: {e}")
        
        logger.info("✅ Migration complete!")


if __name__ == "__main__":
    asyncio.run(migrate())

