import asyncio
import logging
from sqlalchemy import text
from backend_v2.db.session import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate_llm_trace")

async def migrate():
    """Add user_id and mood_id columns to llm_trace table."""
    logger.info("Starting llm_trace migration...")
    
    async with engine.begin() as conn:
        # Check if columns exist
        result = await conn.execute(text("PRAGMA table_info(llm_trace)"))
        columns = [row[1] for row in result.fetchall()]
        
        # Add user_id if missing
        if "user_id" not in columns:
            logger.info("Adding user_id column")
            await conn.execute(text("ALTER TABLE llm_trace ADD COLUMN user_id VARCHAR(36)"))
            await conn.execute(text("CREATE INDEX ix_llm_trace_user_id ON llm_trace (user_id)"))
            
        # Add mood_id if missing
        if "mood_id" not in columns:
            logger.info("Adding mood_id column")
            await conn.execute(text("ALTER TABLE llm_trace ADD COLUMN mood_id VARCHAR(36)"))
            
    logger.info("Migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
