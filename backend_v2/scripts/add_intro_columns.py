import sqlite3
import os

DB_PATH = "data/persistence.db"

def migrate():
    # Handle running from root or backend_v2
    path = DB_PATH
    if not os.path.exists(path):
        # Try adjusting path if running from inside backend_v2
        path = "../data/persistence.db"
        if not os.path.exists(path):
            path = "c:\\Users\\JamiePC\\Desktop\\ai-djv2\\data\\persistence.db"
    
    if not os.path.exists(path):
        print(f"Database not found at {path}")
        return

    print(f"Migrating database at: {path}")
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    
    try:
        # Check columns
        cursor.execute("PRAGMA table_info(moods)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "intro_segment_path" not in columns:
            print("Adding intro_segment_path column...")
            cursor.execute("ALTER TABLE moods ADD COLUMN intro_segment_path TEXT")
        else:
            print("intro_segment_path already exists.")
            
        if "intro_song_uuid" not in columns:
            print("Adding intro_song_uuid column...")
            cursor.execute("ALTER TABLE moods ADD COLUMN intro_song_uuid TEXT")
        else:
            print("intro_song_uuid already exists.")
            
        conn.commit()
        print("Migration complete!")
        
    except Exception as e:
        print(f"Error migrating: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
