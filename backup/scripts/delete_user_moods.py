"""Delete all moods for a user to allow re-onboarding.

Usage:
    python backend_v2/scripts/delete_user_moods.py [email]
    
If no email provided, deletes moods for the most recent user.
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/persistence.db")

def delete_moods(user_email: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Find user
    if user_email:
        cursor.execute("SELECT id, email FROM users WHERE email = ?", (user_email,))
    else:
        cursor.execute("SELECT id, email FROM users ORDER BY created_at DESC LIMIT 1")
    
    user = cursor.fetchone()
    if not user:
        print("❌ No user found")
        conn.close()
        return
    
    user_id, email = user
    print(f"\n👤 User: {email} ({user_id})")
    
    # Count moods
    cursor.execute("SELECT COUNT(*) FROM moods WHERE user_id = ?", (user_id,))
    mood_count = cursor.fetchone()[0]
    
    if mood_count == 0:
        print("✓ No moods to delete")
        conn.close()
        return
    
    # Show moods
    cursor.execute("""
        SELECT id, name, energy_target, valence_target, intro_segment_path 
        FROM moods 
        WHERE user_id = ?
        ORDER BY created_at
    """, (user_id,))
    
    moods = cursor.fetchall()
    print(f"\n🎵 Found {mood_count} moods:")
    for mood_id, name, energy, valence, intro_path in moods:
        intro_status = "✓ has intro" if intro_path else "✗ no intro"
        print(f"  - {name} (Energy: {energy}, Valence: {valence}) [{intro_status}]")
    
    # Confirm
    response = input(f"\n⚠ Delete all {mood_count} moods for {email}? (y/N): ")
    if response.lower() != 'y':
        print("Cancelled.")
        conn.close()
        return
    
    # Delete moods (cascades to mood_profiles)
    cursor.execute("DELETE FROM moods WHERE user_id = ?", (user_id,))
    deleted = cursor.rowcount
    conn.commit()
    
    print(f"\n✅ Deleted {deleted} moods")
    print(f"\nYou can now re-onboard as {email} to test the fix.")
    
    # Reset onboarded flag
    cursor.execute("UPDATE user_profile SET has_onboarded = 0 WHERE user_id = ?", (user_id,))
    if cursor.rowcount > 0:
        conn.commit()
        print("✅ Reset onboarding status")
    
    conn.close()


if __name__ == "__main__":
    email = sys.argv[1] if len(sys.argv) > 1 else None
    delete_moods(email)

