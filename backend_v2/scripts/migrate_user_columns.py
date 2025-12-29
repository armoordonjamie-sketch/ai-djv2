"""Migration script to add user_id columns to existing tables.

This script adds the missing user_id, mood_id, context_id columns to:
- sessions
- play_history  
- segments
- llm_traces

Run with: python -m backend_v2.scripts.migrate_user_columns
"""
import sqlite3
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default database path
DB_PATH = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/persistence.db")
# Extract actual path from SQLAlchemy URL
if ":///" in DB_PATH:
    DB_FILE = DB_PATH.split("///")[-1]
else:
    DB_FILE = "data/persistence.db"


def get_table_columns(conn: sqlite3.Connection, table_name: str) -> list:
    """Get list of column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    columns = get_table_columns(conn, table_name)
    return column_name in columns


def add_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_type: str):
    """Add a column to a table if it doesn't exist."""
    if column_exists(conn, table_name, column_name):
        logger.info(f"  Column {column_name} already exists in {table_name}")
        return False
    
    sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
    logger.info(f"  Adding column: {sql}")
    conn.execute(sql)
    return True


def create_index(conn: sqlite3.Connection, index_name: str, table_name: str, column_name: str):
    """Create an index if it doesn't exist."""
    # Check if index exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,)
    )
    if cursor.fetchone():
        logger.info(f"  Index {index_name} already exists")
        return False
    
    sql = f"CREATE INDEX {index_name} ON {table_name}({column_name})"
    logger.info(f"  Creating index: {sql}")
    conn.execute(sql)
    return True


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Check if a table exists."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def migrate():
    """Run the migration."""
    logger.info(f"Migrating database: {DB_FILE}")
    
    if not Path(DB_FILE).exists():
        logger.error(f"Database file not found: {DB_FILE}")
        return False
    
    conn = sqlite3.connect(DB_FILE)
    
    try:
        # ========================================
        # Add user_id columns to sessions
        # ========================================
        if table_exists(conn, "sessions"):
            logger.info("Migrating sessions table...")
            add_column(conn, "sessions", "user_id", "TEXT")
            add_column(conn, "sessions", "mood_id", "TEXT")
            add_column(conn, "sessions", "context_id", "TEXT")
            create_index(conn, "ix_sessions_user_id", "sessions", "user_id")
        else:
            logger.info("sessions table doesn't exist, skipping")
        
        # ========================================
        # Add user_id columns to play_history
        # ========================================
        if table_exists(conn, "play_history"):
            logger.info("Migrating play_history table...")
            add_column(conn, "play_history", "user_id", "TEXT")
            add_column(conn, "play_history", "mood_id", "TEXT")
            create_index(conn, "ix_play_history_user_id", "play_history", "user_id")
        else:
            logger.info("play_history table doesn't exist, skipping")
        
        # ========================================
        # Add user_id columns to segments
        # ========================================
        if table_exists(conn, "segments"):
            logger.info("Migrating segments table...")
            add_column(conn, "segments", "user_id", "TEXT")
            add_column(conn, "segments", "mood_id", "TEXT")
            create_index(conn, "ix_segments_user_id", "segments", "user_id")
        else:
            logger.info("segments table doesn't exist, skipping")
        
        # ========================================
        # Add user_id columns to llm_traces
        # ========================================
        if table_exists(conn, "llm_traces"):
            logger.info("Migrating llm_traces table...")
            add_column(conn, "llm_traces", "user_id", "TEXT")
            add_column(conn, "llm_traces", "mood_id", "TEXT")
            create_index(conn, "ix_llm_traces_user_id", "llm_traces", "user_id")
        else:
            logger.info("llm_traces table doesn't exist, skipping")
        
        conn.commit()
        logger.info("✅ Migration completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()



if __name__ == "__main__":
    migrate()
