import sqlite3
from pathlib import Path

DB_PATH = Path("data/persistence.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check llm_trace schema
print("\n=== llm_trace table schema ===")
cursor.execute("PRAGMA table_info(llm_trace)")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]}: {col[2]} (nullable={col[3]==0})")

# Check foreign keys
print("\n=== llm_trace foreign keys ===")
cursor.execute("PRAGMA foreign_key_list(llm_trace)")
fks = cursor.fetchall()
if fks:
    for fk in fks:
        print(f"  {fk[3]} -> {fk[2]}.{fk[4]} (on_delete={fk[6]})")
else:
    print("  (none)")

# Check moods table for intro columns
print("\n=== moods table schema (intro columns) ===")
cursor.execute("PRAGMA table_info(moods)")
columns = cursor.fetchall()
for col in columns:
    if 'intro' in col[1]:
        print(f"  {col[1]}: {col[2]}")

# Check if any moods have intro_segment_path set
print("\n=== Moods with pre-generated intros ===")
cursor.execute("SELECT id, name, intro_segment_path, intro_song_uuid FROM moods WHERE intro_segment_path IS NOT NULL")
moods_with_intros = cursor.fetchall()
if moods_with_intros:
    for mood in moods_with_intros:
        print(f"  {mood[1]}: {mood[2]} (song: {mood[3]})")
else:
    print("  (none found)")

conn.close()

