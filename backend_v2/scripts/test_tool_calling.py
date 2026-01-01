"""
Test Tool Calling Integration

Tests the new tool-based track selector with database tools.
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend_v2.db.session import get_db_session
from backend_v2.services.preference_bundle import build_preference_bundle
from backend_v2.orchestration.state import DJState
from backend_v2.orchestration.tool_based_selector import select_track_with_tools
from backend_v2.models.user import User
from sqlalchemy import select

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("test-tool-calling")


async def test_tool_calling():
    """Test tool-based track selection."""
    
    print("\n" + "="*80)
    print("TESTING TOOL-BASED TRACK SELECTION")
    print("="*80 + "\n")
    
    async with get_db_session() as db:
        # Find test user
        result = await db.execute(
            select(User).where(User.email == "test@a.com")
        )
        user = result.scalars().first()
        
        if not user:
            print("❌ Test user not found (test@a.com)")
            return
        
        print(f"✅ Found test user: {user.email} (ID: {user.id})")
        
        # Build preference bundle
        print("\n📦 Building preference bundle...")
        bundle = await build_preference_bundle(
            db=db,
            user_id=user.id,
            context_key="default",
            mood_id=None,  # Will use default mood
            history_limit=100,
        )
        
        if not bundle:
            print("❌ Failed to build preference bundle")
            return
        
        print(f"✅ Bundle built: mood={bundle.mood.name if bundle.mood else 'None'}, history={len(bundle.history.recent_tracks)}")
        
        # Create DJ state
        state = DJState(
            user_id=user.id,
            session_id="test-session-001",
            mood_id=bundle.mood.id if bundle.mood else None,
        )
        
        # Test tool-based selection
        print("\n🤖 Starting tool-based selection...")
        print("   This will call the AI with database tools enabled.")
        print("   Watch for tool calls in the logs!\n")
        
        try:
            song = await select_track_with_tools(
                db=db,
                bundle=bundle,
                state=state,
                prev_song=None,
                max_iterations=5,
            )
            
            if song:
                print("\n" + "="*80)
                print("✅ SELECTION SUCCESSFUL")
                print("="*80)
                print(f"Artist: {song.get('artist')}")
                print(f"Title: {song.get('title')}")
                print(f"Rationale: {song.get('rationale', 'N/A')}")
                print(f"Method: {song.get('selection_method', 'N/A')}")
                print("="*80 + "\n")
            else:
                print("\n❌ Selection failed - no song returned\n")
        
        except Exception as e:
            print(f"\n❌ Error during selection: {e}\n")
            import traceback
            traceback.print_exc()


async def test_individual_tools():
    """Test individual database tools."""
    from backend_v2.integrations.db_tools import (
        get_play_history,
        get_artist_play_count,
        search_songs_in_library,
        get_spotify_context,
    )
    
    print("\n" + "="*80)
    print("TESTING INDIVIDUAL DATABASE TOOLS")
    print("="*80 + "\n")
    
    async with get_db_session() as db:
        # Find test user
        result = await db.execute(
            select(User).where(User.email == "test@a.com")
        )
        user = result.scalars().first()
        
        if not user:
            print("❌ Test user not found")
            return
        
        print(f"Testing with user: {user.email}\n")
        
        # Test 1: Get play history
        print("1️⃣ Testing get_play_history...")
        history = await get_play_history(db, user.id, limit=10)
        print(f"   ✅ Found {len(history)} recent plays")
        if history:
            print(f"   Last play: {history[0].get('artist')} - {history[0].get('title')}")
        
        # Test 2: Get artist play count
        print("\n2️⃣ Testing get_artist_play_count...")
        if history:
            test_artist = history[0].get('artist')
            count_result = await get_artist_play_count(db, user.id, test_artist, last_n_tracks=10)
            print(f"   ✅ {test_artist}: {count_result.get('play_count')} plays in last 10 tracks ({count_result.get('percentage')}%)")
        
        # Test 3: Search songs in library
        print("\n3️⃣ Testing search_songs_in_library...")
        songs = await search_songs_in_library(db, genre="pop", limit=5)
        print(f"   ✅ Found {len(songs)} pop songs")
        if songs:
            print(f"   Example: {songs[0].get('artist')} - {songs[0].get('title')}")
        
        # Test 4: Get Spotify context
        print("\n4️⃣ Testing get_spotify_context...")
        spotify_ctx = await get_spotify_context(db, user.id)
        if spotify_ctx:
            print(f"   ✅ Top artists: {len(spotify_ctx.get('top_artists', []))}")
            print(f"   ✅ Top genres: {spotify_ctx.get('top_genres', [])[:5]}")
        else:
            print("   ⚠️  No Spotify context found")
        
        print("\n" + "="*80)
        print("✅ ALL TOOL TESTS COMPLETED")
        print("="*80 + "\n")


async def main():
    """Run all tests."""
    print("\n[TEST] Starting Tool Calling Tests\n")
    
    # Test 1: Individual tools
    await test_individual_tools()
    
    # Test 2: Full tool-based selection
    await test_tool_calling()
    
    print("[DONE] All tests completed!\n")


if __name__ == "__main__":
    asyncio.run(main())

