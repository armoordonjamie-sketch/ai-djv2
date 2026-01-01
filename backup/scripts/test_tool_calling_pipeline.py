"""
Test script for the new tool calling pipeline.

Tests all new tools, enhanced tools, and migrated agents using the actual database.
Run with: python -m backend_v2.scripts.test_tool_calling_pipeline
"""
import asyncio
import logging
import sys
from typing import Optional

from sqlalchemy import select

from backend_v2.db.session import get_db_session
from backend_v2.integrations.db_tools import (
    execute_tool,
    get_play_history,
    get_artist_play_count,
    search_songs_in_library,
    get_user_feedback,
    get_spotify_context,
    analyze_listening_patterns,
    get_mood_details,
    get_user_moods,
    get_user_profile,
    get_mood_profile,
    get_song_details,
    get_session_info,
    get_track_intents,
    get_feedback_summary,
)
from backend_v2.models.user import User
from backend_v2.models.mood import Mood
from backend_v2.services.mood_enrichment import enrich_mood_with_llm
from backend_v2.services.training import regenerate_summary_text
from backend_v2.services.preference_bundle import build_preference_bundle

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test-tool-calling")


async def get_user_by_email(db, email: str) -> Optional[User]:
    """Get user by email."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def test_new_tools(db, user_id: str):
    """Test all 8 new tools."""
    print("\n" + "="*80)
    print("TESTING NEW TOOLS")
    print("="*80)
    
    # Test 1: get_mood_details
    print("\n1. Testing get_mood_details...")
    try:
        # Get user's moods first
        moods_result = await db.execute(select(Mood).where(Mood.user_id == user_id).limit(1))
        mood = moods_result.scalar_one_or_none()
        
        if mood:
            result = await execute_tool("get_mood_details", {"mood_id": mood.id}, db)
            print(f"   [OK] get_mood_details: Found mood '{result.get('name')}' with {len(result.get('genres', []))} genres")
            print(f"      Profile version: {result.get('profile', {}).get('version', 'N/A')}")
        else:
            print("   [WARN] No moods found for user")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    # Test 2: get_user_moods
    print("\n2. Testing get_user_moods...")
    try:
        result = await execute_tool("get_user_moods", {"user_id": user_id}, db)
        print(f"   [OK] get_user_moods: Found {len(result)} moods")
        for mood in result[:3]:
            print(f"      - {mood.get('name')} (default: {mood.get('is_default')})")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    # Test 3: get_user_profile
    print("\n3. Testing get_user_profile...")
    try:
        result = await execute_tool("get_user_profile", {"user_id": user_id}, db)
        if result:
            print(f"   [OK] get_user_profile: Found profile")
            print(f"      Display name: {result.get('display_name', 'N/A')}")
            print(f"      Favorite genres: {len(result.get('favorite_genres', []))}")
            print(f"      Favorite artists: {len(result.get('favorite_artists', []))}")
        else:
            print("   [WARN] No profile found")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    # Test 4: get_mood_profile
    print("\n4. Testing get_mood_profile...")
    try:
        moods_result = await db.execute(select(Mood).where(Mood.user_id == user_id).limit(1))
        mood = moods_result.scalar_one_or_none()
        
        if mood:
            result = await execute_tool("get_mood_profile", {"mood_id": mood.id}, db)
            if result:
                print(f"   [OK] get_mood_profile: Found profile version {result.get('version')}")
                print(f"      Summary: {result.get('summary_text', 'None')[:50]}...")
            else:
                print("   [WARN] No profile found")
        else:
            print("   [WARN] No moods found")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    # Test 5: get_song_details
    print("\n5. Testing get_song_details...")
    try:
        from backend_v2.models.existing import Song
        songs_result = await db.execute(select(Song).limit(1))
        song = songs_result.scalar_one_or_none()
        
        if song:
            result = await execute_tool("get_song_details", {"song_uuid": song.uuid}, db)
            if result:
                print(f"   [OK] get_song_details: Found '{result.get('title')}' by {result.get('artist')}")
                print(f"      Has features: {result.get('features') is not None}")
                print(f"      Has lyrics analysis: {result.get('lyrics_analysis') is not None}")
            else:
                print("   [WARN] Song not found")
        else:
            print("   [WARN] No songs in database")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    # Test 6: get_session_info
    print("\n6. Testing get_session_info...")
    try:
        result = await execute_tool("get_session_info", {"user_id": user_id}, db)
        print(f"   [OK] get_session_info: Found {len(result)} sessions")
        for session in result[:2]:
            print(f"      - Session {session.get('session_id')[:8]}... (active: {session.get('is_active')})")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    # Test 7: get_track_intents
    print("\n7. Testing get_track_intents...")
    try:
        result = await execute_tool("get_track_intents", {"user_id": user_id, "limit": 10}, db)
        print(f"   [OK] get_track_intents: Found {len(result)} intents")
        for intent in result[:3]:
            print(f"      - {intent.get('artist')} - {intent.get('title')} ({intent.get('status')})")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    # Test 8: get_feedback_summary
    print("\n8. Testing get_feedback_summary...")
    try:
        result = await execute_tool("get_feedback_summary", {"user_id": user_id, "days": 30}, db)
        if result and not result.get("error"):
            print(f"   [OK] get_feedback_summary:")
            print(f"      Total feedback: {result.get('total_feedback')}")
            print(f"      Likes: {result.get('likes')}, Dislikes: {result.get('dislikes')}")
            print(f"      Like ratio: {result.get('like_ratio')}%")
        else:
            print(f"   [WARN] {result.get('error', 'No feedback found')}")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")


async def test_enhanced_tools(db, user_id: str):
    """Test enhanced existing tools."""
    print("\n" + "="*80)
    print("TESTING ENHANCED TOOLS")
    print("="*80)
    
    # Test 1: Enhanced search_songs_in_library
    print("\n1. Testing enhanced search_songs_in_library...")
    try:
        result = await execute_tool("search_songs_in_library", {"limit": 5}, db)
        print(f"   [OK] search_songs_in_library: Found {len(result)} songs")
        if result:
            song = result[0]
            print(f"      First song: {song.get('title')} by {song.get('artist')}")
            print(f"      Has features: {song.get('energy') is not None}")
            print(f"      Has lyrics analysis: {song.get('lyrics_analysis') is not None}")
            print(f"      Has external IDs: {song.get('external_ids') is not None}")
            print(f"      Has play stats: {song.get('play_statistics') is not None}")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    # Test 2: Enhanced get_play_history
    print("\n2. Testing enhanced get_play_history...")
    try:
        result = await execute_tool("get_play_history", {"user_id": user_id, "limit": 5}, db)
        print(f"   [OK] get_play_history: Found {len(result)} history items")
        if result:
            item = result[0]
            print(f"      First item: {item.get('title')} by {item.get('artist')}")
            print(f"      Has features: {item.get('features') is not None}")
            print(f"      Has genres: {len(item.get('genres', []))} genres")
            print(f"      Has external IDs: {item.get('external_ids') is not None}")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    # Test 3: Enhanced analyze_listening_patterns
    print("\n3. Testing enhanced analyze_listening_patterns...")
    try:
        result = await execute_tool("analyze_listening_patterns", {"user_id": user_id, "days": 30}, db)
        if result and not result.get("error"):
            print(f"   [OK] analyze_listening_patterns:")
            print(f"      Total plays: {result.get('total_plays')}")
            print(f"      Unique artists: {result.get('unique_artists')}")
            print(f"      Mood analysis: {result.get('mood_analysis') is not None}")
            print(f"      Genre distribution: {len(result.get('genre_distribution', []))} genres")
            print(f"      Energy trends: {result.get('energy_trends') is not None}")
            print(f"      Valence trends: {result.get('valence_trends') is not None}")
        else:
            print(f"   [WARN] {result.get('error', 'No data')}")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    # Test 4: Fixed get_spotify_context
    print("\n4. Testing fixed get_spotify_context...")
    try:
        result = await execute_tool("get_spotify_context", {"user_id": user_id}, db)
        if result:
            print(f"   [OK] get_spotify_context: Found Spotify context")
            print(f"      Has top artists: {result.get('top_artists') is not None}")
            print(f"      Has favorite tracks: {len(result.get('favorite_tracks_with_stats', []))} tracks")
            print(f"      Has genres analysis: {result.get('genres_analysis') is not None}")
        else:
            print("   [WARN] No Spotify context found")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")


async def test_migrated_agents(db, user_id: str):
    """Test migrated agents."""
    print("\n" + "="*80)
    print("TESTING MIGRATED AGENTS")
    print("="*80)
    
    # Test 1: mood_enrichment with tools
    print("\n1. Testing mood_enrichment with tools...")
    try:
        moods_result = await db.execute(select(Mood).where(Mood.user_id == user_id).limit(1))
        mood = moods_result.scalar_one_or_none()
        
        if mood:
            print(f"   Testing with mood: {mood.name}")
            # Test with tools enabled
            success = await enrich_mood_with_llm(db, mood, user_profile=None, use_tools=True)
            if success:
                print(f"   [OK] mood_enrichment with tools: Success")
            else:
                print(f"   [WARN] mood_enrichment with tools: Failed (may be expected if OpenRouter disabled)")
        else:
            print("   [WARN] No moods found")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: training with tools
    print("\n2. Testing training regenerate_summary_text with tools...")
    try:
        moods_result = await db.execute(select(Mood).where(Mood.user_id == user_id).limit(1))
        mood = moods_result.scalar_one_or_none()
        
        if mood:
            print(f"   Testing with mood: {mood.name}")
            summary = await regenerate_summary_text(db, mood.id, limit=20, use_tools=True)
            if summary:
                print(f"   [OK] regenerate_summary_text with tools: Success")
                print(f"      Summary: {summary[:100]}...")
            else:
                print(f"   [WARN] regenerate_summary_text: No summary generated (may be expected if no feedback)")
        else:
            print("   [WARN] No moods found")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: preference bundle (used by agents)
    print("\n3. Testing preference bundle (used by agents)...")
    try:
        moods_result = await db.execute(select(Mood).where(Mood.user_id == user_id).limit(1))
        mood = moods_result.scalar_one_or_none()
        
        if mood:
            bundle = await build_preference_bundle(
                db=db,
                user_id=user_id,
                session_id="test-session-123",
                mood_id=mood.id,
                use_cache=False
            )
            print(f"   [OK] Preference bundle built:")
            print(f"      Mood: {bundle.mood.name}")
            print(f"      Likes: {len(bundle.feedback.recent_likes)}")
            print(f"      Dislikes: {len(bundle.feedback.recent_dislikes)}")
            print(f"      History: {len(bundle.history.recent_plays)} plays")
        else:
            print("   [WARN] No moods found")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main test function."""
    print("="*80)
    print("TOOL CALLING PIPELINE TEST")
    print("="*80)
    print("Testing with user: test@a.com")
    
    async with get_db_session() as db:
        # Get user
        user = await get_user_by_email(db, "test@a.com")
        
        if not user:
            print("\n[ERROR] ERROR: User 'test@a.com' not found in database!")
            print("   Please ensure the user exists before running tests.")
            sys.exit(1)
        
        user_id = user.id
        print(f"   Found user: {user.email} (ID: {user_id})")
        
        # Run tests
        await test_new_tools(db, user_id)
        await test_enhanced_tools(db, user_id)
        await test_migrated_agents(db, user_id)
        
        print("\n" + "="*80)
        print("TEST COMPLETE")
        print("="*80)


if __name__ == "__main__":
    asyncio.run(main())

