"""Migration script to add metadata columns to the songs table.

This script adds columns for:
- ISRC (International Standard Recording Code)
- MusicBrainz IDs (recording, release, artist)
- Apple Music ID
- Artwork URL
- Genres and tags (JSON)

Run with: python -m backend_v2.scripts.migrate_metadata_columns
"""
import sqlite3
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default database path
DB_PATH = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/persistence.db")
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
        if not table_exists(conn, "songs"):
            logger.error("songs table doesn't exist")
            return False
        
        logger.info("Adding metadata columns to songs table...")
        
        # Canonical IDs
        add_column(conn, "songs", "isrc", "TEXT")
        add_column(conn, "songs", "recording_mbid", "TEXT")
        add_column(conn, "songs", "release_mbid", "TEXT")
        add_column(conn, "songs", "artist_mbid", "TEXT")
        add_column(conn, "songs", "apple_song_id", "TEXT")
        
        # Artwork
        add_column(conn, "songs", "artwork_url", "TEXT")
        
        # Genres and tags (JSON arrays)
        add_column(conn, "songs", "genres", "TEXT")  # JSON array
        add_column(conn, "songs", "tags", "TEXT")    # JSON array
        
        # Create indexes for common lookups
        create_index(conn, "ix_songs_isrc", "songs", "isrc")
        create_index(conn, "ix_songs_recording_mbid", "songs", "recording_mbid")
        create_index(conn, "ix_songs_apple_song_id", "songs", "apple_song_id")
        
        conn.commit()
        logger.info("✅ Metadata columns migration completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
