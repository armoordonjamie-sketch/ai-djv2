"""Migration script to add onboarded_at column to users table.

Run with: python -m backend_v2.scripts.migrate_onboarded_at
"""
import asyncio
import logging
import sqlite3
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_sync():
    """Add onboarded_at column to users table."""
    db_path = os.getenv("DB_PATH", "data/persistence.db")
    
    if not os.path.exists(db_path):
        logger.error(f"Database not found at {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "onboarded_at" in columns:
            logger.info("Column 'onboarded_at' already exists in users table")
            return True
        
        # Add the column
        logger.info("Adding 'onboarded_at' column to users table...")
        cursor.execute("""
            ALTER TABLE users ADD COLUMN onboarded_at DATETIME DEFAULT NULL
        """)
        conn.commit()
        
        logger.info("✅ Successfully added 'onboarded_at' column to users table")
        
        # Optionally: Mark all existing users as onboarded
        cursor.execute("UPDATE users SET onboarded_at = datetime('now') WHERE onboarded_at IS NULL")
        affected = cursor.rowcount
        conn.commit()
        logger.info(f"✅ Marked {affected} existing users as onboarded")
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = migrate_sync()
    exit(0 if success else 1)
