
import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add project root to sys.path
sys.path.append(os.getcwd())

from backend_v2.services.preference_bundle import get_scored_candidates, PreferenceBundle
from backend_v2.orchestration.agents import acquire_song_by_name

async def test_artwork_propagation():
    print("\nRunning test: test_artwork_propagation")
    
    # Mock DB session
    db = AsyncMock()
    
    # Mock Song model
    mock_song = MagicMock()
    mock_song.uuid = "test-uuid"
    mock_song.title = "Test Title"
    mock_song.artist = "Test Artist"
    mock_song.local_path = "/path/to/song.mp3"
    mock_song.duration_sec = 180.0
    mock_song.artwork_url = "https://example.com/artwork.jpg"
    mock_song.features = MagicMock()
    mock_song.features.energy = 0.8
    mock_song.features.tempo = 120.0
    # ... other features ...
    
    # 1. Test get_scored_candidates propagation
    # We need to mock the DB result for get_scored_candidates
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_song]
    db.execute.return_value = mock_result
    
    bundle = MagicMock(spec=PreferenceBundle)
    bundle.user_id = "test-user"
    bundle.history = MagicMock()
    bundle.history.recent_plays = []
    bundle.history.recent_tracks = []
    bundle.get_disliked_artists.return_value = []
    bundle.mood = MagicMock()
    bundle.mood.id = "test-mood"
    bundle.mood.mood_profile = MagicMock()
    bundle.mood.mood_profile.name = "Test Mood"
    
    scored = await get_scored_candidates(db, bundle)
    if scored:
        song_dict, score = scored[0]
        print(f"Scored song artwork_url: {song_dict.get('artwork_url')}")
        assert song_dict.get('artwork_url') == "https://example.com/artwork.jpg"
        print("✓ get_scored_candidates propagated artwork_url")
    else:
        print("✗ get_scored_candidates failed to return songs")

    # 2. Test acquire_song_by_name propagation
    # Reset mock for acquire_song_by_name (which searches ilike)
    mock_result_acquire = MagicMock()
    mock_result_acquire.scalars().first.return_value = mock_song
    db.execute.return_value = mock_result_acquire
    
    acquired = await acquire_song_by_name(db, "Test Artist", "Test Title")
    if acquired:
        print(f"Acquired song artwork_url: {acquired.get('artwork_url')}")
        assert acquired.get('artwork_url') == "https://example.com/artwork.jpg"
        print("✓ acquire_song_by_name propagated artwork_url")
    else:
        print("✗ acquire_song_by_name failed to return song")

if __name__ == "__main__":
    asyncio.run(test_artwork_propagation())
