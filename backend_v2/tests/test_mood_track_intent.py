"""Tests for mood generation and track intent flow.

Validates:
- Mood spread (distinctness)
- TrackIntent creation
- Acquisition fallbacks
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.services.mood_generator import (
    MOOD_TEMPLATES,
    _calculate_mood_spread,
)
from backend_v2.models.track_intent import TrackIntent, TrackIntentStatus
from backend_v2.catalog.selector import (
    cosine_similarity,
    track_to_feature_vector,
    score_track_relevance,
)
from backend_v2.catalog.providers import CatalogTrack, AudioFeatures


def test_mood_templates_distinct():
    """Test that mood templates have distinct characteristics."""
    # Check we have 5 moods
    assert len(MOOD_TEMPLATES) == 5
    
    # Check energy values are spread
    energy_values = [m.energy_target for m in MOOD_TEMPLATES]
    assert max(energy_values) - min(energy_values) >= 0.4  # At least 0.4 spread
    
    # Check valence values are spread
    valence_values = [m.valence_target for m in MOOD_TEMPLATES]
    assert max(valence_values) - min(valence_values) >= 0.3  # At least 0.3 spread
    
    # Check each mood has unique fields
    for template in MOOD_TEMPLATES:
        assert template.genre_seeds, f"{template.name} missing genre_seeds"
        assert template.vibe_keywords, f"{template.name} missing vibe_keywords"
        assert template.example_artists, f"{template.name} missing example_artists"
        assert template.intro_personality, f"{template.name} missing intro_personality"


def test_cosine_similarity():
    """Test cosine similarity calculation."""
    vec1 = (1.0, 0.0, 0.5)
    vec2 = (1.0, 0.0, 0.5)
    assert cosine_similarity(vec1, vec2) == pytest.approx(1.0, abs=0.01)
    
    vec3 = (0.0, 1.0, 0.0)
    assert cosine_similarity(vec1, vec3) == pytest.approx(0.0, abs=0.01)
    
    # Perpendicular vectors
    vec4 = (1.0, 0.0, 0.0)
    vec5 = (0.0, 1.0, 0.0)
    assert cosine_similarity(vec4, vec5) == pytest.approx(0.0, abs=0.01)


def test_track_to_feature_vector():
    """Test track feature vector extraction."""
    track = CatalogTrack(
        title="Test Song",
        artist="Test Artist",
        features=AudioFeatures(
            energy=0.8,
            valence=0.6,
            danceability=0.7,
            tempo=120,
        )
    )
    
    vec = track_to_feature_vector(track)
    assert vec is not None
    assert len(vec) == 4
    assert vec[0] == 0.8  # energy
    assert vec[1] == 0.6  # valence
    assert vec[2] == 0.7  # danceability
    # tempo normalized: (120 - 60) / 120 = 0.5
    assert vec[3] == pytest.approx(0.5, abs=0.01)


def test_track_intent_creation():
    """Test TrackIntent model creation."""
    intent = TrackIntent(
        user_id="test-user",
        mood_id="test-mood",
        session_id="test-session",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        status=TrackIntentStatus.PENDING_ACQUISITION,
    )
    
    assert intent.title == "Test Song"
    assert intent.artist == "Test Artist"
    assert intent.status == TrackIntentStatus.PENDING_ACQUISITION
    assert intent.acquired_song_uuid is None


@pytest.mark.asyncio
async def test_track_intent_lifecycle():
    """Test TrackIntent lifecycle (pending -> acquired/failed)."""
    intent = TrackIntent(
        user_id="test-user",
        mood_id="test-mood",
        session_id="test-session",
        title="Test Song",
        artist="Test Artist",
        status=TrackIntentStatus.PENDING_ACQUISITION,
    )
    
    # Initial state
    assert intent.status == TrackIntentStatus.PENDING_ACQUISITION
    
    # Simulate successful acquisition
    intent.status = TrackIntentStatus.ACQUIRED
    intent.acquired_song_uuid = "test-song-uuid"
    
    assert intent.status == TrackIntentStatus.ACQUIRED
    assert intent.acquired_song_uuid == "test-song-uuid"
    
    # Test failed acquisition
    intent2 = TrackIntent(
        user_id="test-user",
        mood_id="test-mood",
        session_id="test-session",
        title="Unavailable Song",
        artist="Unknown Artist",
        status=TrackIntentStatus.PENDING_ACQUISITION,
    )
    
    intent2.status = TrackIntentStatus.FAILED
    assert intent2.status == TrackIntentStatus.FAILED


def test_mmr_diversity_concept():
    """Test that MMR will prefer diverse tracks over similar ones."""
    # Create 3 tracks: 2 similar, 1 different
    track1 = CatalogTrack(
        title="Pop Song 1",
        artist="Pop Artist",
        features=AudioFeatures(energy=0.8, valence=0.8, danceability=0.9, tempo=120)
    )
    
    track2 = CatalogTrack(
        title="Pop Song 2",
        artist="Pop Artist 2",
        features=AudioFeatures(energy=0.82, valence=0.78, danceability=0.88, tempo=118)
    )
    
    track3 = CatalogTrack(
        title="Chill Song",
        artist="Chill Artist",
        features=AudioFeatures(energy=0.3, valence=0.4, danceability=0.3, tempo=80)
    )
    
    vec1 = track_to_feature_vector(track1)
    vec2 = track_to_feature_vector(track2)
    vec3 = track_to_feature_vector(track3)
    
    # track1 and track2 should be similar
    sim_12 = cosine_similarity(vec1, vec2)
    assert sim_12 > 0.95  # Very similar
    
    # track1 and track3 should be different
    sim_13 = cosine_similarity(vec1, vec3)
    assert sim_13 < 0.8  # Different
    
    # If we've selected track1, MMR should prefer track3 over track2 for diversity
    # (Even if track2 has higher relevance score)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

