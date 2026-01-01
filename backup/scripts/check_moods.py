import sqlite3
from pathlib import Path

DB_PATH = Path("data/persistence.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get the most recent user
cursor.execute("SELECT id, email FROM users ORDER BY created_at DESC LIMIT 1")
user = cursor.fetchone()
if user:
    user_id, email = user
    print(f"\n=== Latest user: {email} ({user_id}) ===\n")
    
    # Get their moods
    cursor.execute("""
        SELECT id, name, color, energy_target, valence_target, genres_json, dj_personality, 
               intro_segment_path, intro_song_uuid
        FROM moods 
        WHERE user_id = ?
        ORDER BY created_at
    """, (user_id,))
    
    moods = cursor.fetchall()
    print(f"Moods ({len(moods)} found):")
    for mood in moods:
        mood_id, name, color, energy, valence, genres, personality, intro_path, intro_song = mood
        print(f"\n  {name}:")
        print(f"    Color: {color}")
        print(f"    Energy: {energy}, Valence: {valence}")
        print(f"    Genres: {genres}")
        print(f"    Personality: {personality}")
        print(f"    Intro: {intro_path}")
        print(f"    Song: {intro_song}")
else:
    print("No users found")

conn.close()

