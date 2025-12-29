
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from backend_v2.services.preference_bundle import get_scored_candidates, PreferenceBundle
from backend_v2.orchestration.agents import acquire_song_by_name


@pytest.mark.asyncio
async def test_artwork_propagation():
    """Ensure artwork_url flows through candidate scoring and acquisition."""
    db = AsyncMock()

    mock_song = MagicMock()
    mock_song.uuid = "test-uuid"
    mock_song.title = "Test Title"
    mock_song.artist = "Test Artist"
    mock_song.local_path = "/path/to/song.mp3"
    mock_song.duration_sec = 180.0
    mock_song.artwork_url = "https://example.com/artwork.jpg"
    mock_song.genres = None
    mock_song.tags = None
    mock_song.explicit = False
    mock_song.features = MagicMock()
    mock_song.features.energy = 0.8
    mock_song.features.valence = 0.5
    mock_song.features.tempo = 120.0
    mock_song.features.key = None
    mock_song.features.mode = None
    mock_song.features.danceability = None
    mock_song.features.acousticness = None
    mock_song.features.instrumentalness = None

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_song]
    db.execute.return_value = mock_result

    bundle = MagicMock(spec=PreferenceBundle)
    bundle.user_id = "test-user"
    bundle.history = MagicMock()
    bundle.history.recent_plays = []
    bundle.history.recent_tracks = []
    bundle.history.recent_artists = []
    bundle.get_disliked_song_uuids.return_value = []
    bundle.get_disliked_artists.return_value = []
    bundle.get_favorite_artists.return_value = []
    bundle.get_liked_song_uuids.return_value = []
    bundle.get_no_go_list.return_value = []
    bundle.allows_explicit.return_value = True
    bundle.mood = MagicMock()
    bundle.mood.id = "test-mood"
    bundle.mood.energy_target = 0.5
    bundle.mood.valence_target = 0.5
    bundle.mood_profile = MagicMock()
    bundle.mood_profile.weights_json = None

    scored = await get_scored_candidates(db, bundle)
    assert scored
    song_dict, _score = scored[0]
    assert song_dict.get("artwork_url") == "https://example.com/artwork.jpg"

    mock_result_acquire = MagicMock()
    mock_result_acquire.scalars().first.return_value = mock_song
    db.execute.return_value = mock_result_acquire

    with patch("os.path.exists", return_value=True):
        acquired = await acquire_song_by_name(db, "Test Artist", "Test Title")

    assert acquired
    assert acquired.get("artwork_url") == "https://example.com/artwork.jpg"
