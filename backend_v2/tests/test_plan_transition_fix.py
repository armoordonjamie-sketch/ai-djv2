
import asyncio
import logging
import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from backend_v2.orchestration.agents import plan_transition
from backend_v2.services.preference_bundle import PreferenceBundle, MoodData
from unittest.mock import MagicMock, AsyncMock

# Configure logging
logging.basicConfig(level=logging.INFO)

async def test_plan_transition_null_features():
    print("\nRunning test: test_plan_transition_null_features")
    
    # Mock DB session
    db = AsyncMock()
    
    # Mock Bundle
    bundle = MagicMock(spec=PreferenceBundle)
    bundle.user_id = "test-user"
    bundle.session_id = "test-session"
    bundle.mood = MagicMock(spec=MoodData)
    bundle.mood.id = "test-mood"
    
    # Song A with features
    song_a = {
        "uuid": "uuid-a",
        "title": "Song A",
        "artist": "Artist A",
        "features": {"tempo": 120.0, "energy": 0.8}
    }
    
    # Song B with NULL features (This was causing the crash)
    song_b = {
        "uuid": "uuid-b",
        "title": "Song B",
        "artist": "Artist B",
        "features": None
    }
    
    try:
        # This call should NOT raise AttributeError
        result = await plan_transition(db, bundle, song_a, song_b)
        
        print(f"Result: {result}")
        assert result is not None
        assert "transition_type" in result
        print("Test PASSED: plan_transition handled NULL features successfully.")
        
    except Exception as e:
        print(f"Test FAILED: Received exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_plan_transition_null_features())
