"""Add session persistence columns for resume functionality.

This migration adds columns to track playback position and session state,
enabling users to resume their stream from where they left off.
"""
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger("ai-dj.migration")


def migrate(db_path: str = "data/persistence.db"):
    """Add session persistence columns to sessions table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(sessions)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        columns_to_add = [
            ("playback_position_sec", "REAL DEFAULT 0.0"),
            ("last_heartbeat_at", "TEXT"),
            ("is_active", "INTEGER DEFAULT 1"),
            ("current_song_uuid", "TEXT"),
            ("current_song_title", "TEXT"),
            ("current_song_artist", "TEXT"),
            ("current_song_artwork", "TEXT"),
        ]
        
        for col_name, col_type in columns_to_add:
            if col_name not in existing_columns:
                logger.info(f"Adding column {col_name} to sessions table")
                cursor.execute(f"ALTER TABLE sessions ADD COLUMN {col_name} {col_type}")
            else:
                logger.info(f"Column {col_name} already exists, skipping")
        
        conn.commit()
        logger.info("✅ Session persistence migration complete")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()

