import sqlite3
from pathlib import Path

DB_PATH = Path("data/persistence.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get songs used in intros
song_ids = [
    ('af0f77e9-7d56-4165-834c-b58686f40d37', 'Flow'),
    ('5c10a79b-32e6-4e6f-939c-a0614c20fb6b', 'Energy & Party (DUPLICATE)'),
    ('62422a1f-d2ab-49c8-ad73-28d24b6d5ea5', 'Chill'),
    ('922718f4-856a-4f91-bfc9-30e37c761c02', 'Late Night'),
]

print("\n=== Songs used in intro segments ===\n")
for song_id, mood_name in song_ids:
    cursor.execute("""
        SELECT s.title, s.artist, s.genres, sf.energy, sf.valence
        FROM songs s
        LEFT JOIN song_features sf ON s.uuid = sf.song_uuid
        WHERE s.uuid = ?
    """, (song_id,))
    
    song = cursor.fetchone()
    if song:
        title, artist, genres, energy, valence = song
        print(f"[{mood_name}] {title} - {artist}")
        print(f"  Energy: {energy}, Valence: {valence}")
        print(f"  Genres: {genres}")
        print()
    else:
        print(f"[{mood_name}] Song {song_id} not found\n")

conn.close()
