"""Fix LLM trace foreign key constraint issue.

The issue: During mood intro pre-generation, we use session_id like "pre-gen-{mood_id}"
but these sessions don't exist in the sessions table, causing foreign key violations.

Solution: Make session_id nullable and drop the foreign key constraint so traces
can be stored for pre-generation scenarios without requiring a real session.
"""
import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "persistence.db"


def fix_llm_trace_fk():
    """Remove foreign key constraint on llm_trace.session_id."""
    
    if not DB_PATH.exists():
        logger.error(f"Database not found at {DB_PATH}")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if llm_trace table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llm_trace'")
        if not cursor.fetchone():
            logger.error("llm_trace table doesn't exist")
            return False
        
        logger.info("Backing up llm_trace data...")
        cursor.execute("SELECT * FROM llm_trace")
        rows = cursor.fetchall()
        
        # Get column info
        cursor.execute("PRAGMA table_info(llm_trace)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        logger.info(f"Found {len(rows)} rows in llm_trace")
        
        # SQLite doesn't support dropping constraints directly
        # We need to recreate the table without the FK constraint
        
        logger.info("Recreating llm_trace table without session_id FK constraint...")
        
        # Create new table without FK constraint
        cursor.execute("""
            CREATE TABLE llm_trace_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                user_id TEXT,
                mood_id TEXT,
                agent_name TEXT,
                prompt TEXT,
                response TEXT,
                model TEXT,
                thinking_budget REAL,
                created_at TEXT,
                correlation_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY (mood_id) REFERENCES moods(id) ON DELETE SET NULL
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_llm_trace_new_session_id ON llm_trace_new (session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_llm_trace_new_correlation_id ON llm_trace_new (correlation_id)")
        
        # Copy data
        if rows:
            logger.info("Copying data to new table...")
            placeholders = ','.join(['?' for _ in column_names])
            cursor.executemany(
                f"INSERT INTO llm_trace_new ({','.join(column_names)}) VALUES ({placeholders})",
                rows
            )
        
        # Drop old table and rename new one
        cursor.execute("DROP TABLE llm_trace")
        cursor.execute("ALTER TABLE llm_trace_new RENAME TO llm_trace")
        
        conn.commit()
        logger.info("Successfully fixed llm_trace table - session_id FK constraint removed")
        
        # Verify
        cursor.execute("SELECT COUNT(*) FROM llm_trace")
        count = cursor.fetchone()[0]
        logger.info(f"Verified: llm_trace has {count} rows")
        
        return True
        
    except Exception as e:
        logger.error(f"Error fixing llm_trace: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()


if __name__ == "__main__":
    success = fix_llm_trace_fk()
    if success:
        print("\nDatabase migration completed successfully")
        print("You can now restart the backend server.")
    else:
        print("\nMigration failed - check logs above")

