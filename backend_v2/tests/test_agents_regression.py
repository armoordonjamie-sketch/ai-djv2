"""Regression tests for orchestration agents fixes.

Tests for GitHub issues #2, #3, #4, #5:
- HistoryItem dataclass access
- Fallback signature with correct arguments
- Song.features scalar access (not list)
- Features dict structure in returned songs
- Intent.selection_rationale field name
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from backend_v2.services.preference_bundle import (
    PreferenceBundle,
    ContextData,
    MoodData,
    MoodProfileData,
    FeedbackData,
    HistoryData,
    HistoryItem,
    UserProfileData,
)
from backend_v2.orchestration.state import DJState
from backend_v2.catalog.providers import CatalogTrack, AudioFeatures


@pytest.mark.asyncio
class TestHistoryItemAccess:
    """Test Issue #2: HistoryItem used as dict"""
    
    async def test_catalog_selection_with_nonempty_history(self):
        """Non-empty history with HistoryItem objects doesn't crash."""
        from backend_v2.orchestration.agents import select_track_via_catalog
        
        # Create bundle with HistoryItem objects (dataclass, not dict)
        history_items = [
            HistoryItem(song_uuid="song-1", title="Track 1", artist="Artist 1"),
            HistoryItem(song_uuid="song-2", title="Track 2", artist="Artist 2"),
        ]
        
        bundle = PreferenceBundle(
            user_id="test-user",
            session_id="test-session",
            context=ContextData(id="ctx-1", name="default", raw_text="test"),
            mood=MoodData(
                id="mood-1", name="Test", genres=["pop"],
                energy_target=0.5, valence_target=0.5, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(),
            history=HistoryData(
                recent_plays=["song-1", "song-2"],
                recent_artists=["Artist 1", "Artist 2"],
                recent_tracks=history_items  # HistoryItem objects, not dicts
            ),
            profile=UserProfileData(),
            agent_settings={},
            prompt_templates={},
        )
        
        state = {"session_id": "test-session"}
        
        # Mock database and providers
        db = AsyncMock()
        
        # Mock catalog selector to return None (triggers fallback)
        with patch("backend_v2.orchestration.agents.select_diverse_track") as mock_select:
            mock_select.return_value = None
            
            # Mock local library selection
            with patch("backend_v2.orchestration.agents.get_scored_candidates") as mock_candidates:
                mock_candidates.return_value = []
                
                # Should not crash when accessing HistoryItem attributes
                result = await select_track_via_catalog(
                    db=db,
                    bundle=bundle,
                    state=state,
                    prev_song=None,
                    history_ids=["song-1", "song-2"],
                    use_intent_flow=True
                )
                
                # Should fall back to None (no candidates)
                assert result is None


@pytest.mark.asyncio
class TestFallbackSignature:
    """Test Issue #3: Missing state argument in fallback"""
    
    async def test_fallback_selection_correct_signature(self):
        """Force catalog failure and verify legacy fallback has correct signature."""
        from backend_v2.orchestration.agents import select_track_via_catalog
        
        bundle = PreferenceBundle(
            user_id="test-user",
            session_id="test-session",
            context=ContextData(id="ctx-1", name="default", raw_text="test"),
            mood=MoodData(
                id="mood-1", name="Test", genres=["pop"],
                energy_target=0.5, valence_target=0.5, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(),
            history=HistoryData(),
            profile=UserProfileData(),
            agent_settings={},
            prompt_templates={},
        )
        
        state = {"session_id": "test-session"}
        db = AsyncMock()
        
        # Mock catalog to return None (force fallback)
        with patch("backend_v2.orchestration.agents.select_diverse_track") as mock_select:
            mock_select.return_value = None
            
            # Mock select_track to verify it's called with correct signature
            with patch("backend_v2.orchestration.agents.select_track") as mock_fallback:
                mock_fallback.return_value = None
                
                await select_track_via_catalog(
                    db=db,
                    bundle=bundle,
                    state=state,
                    prev_song=None,
                    history_ids=["song-1"],
                    use_intent_flow=True
                )
                
                # Verify select_track called with all 5 required arguments
                mock_fallback.assert_called_once()
                call_args = mock_fallback.call_args[0]
                assert len(call_args) == 5  # db, bundle, state, prev_song, history_ids
                assert call_args[0] == db
                assert call_args[1] == bundle
                assert call_args[2] == state
                assert call_args[3] is None  # prev_song
                assert call_args[4] == ["song-1"]  # history_ids


@pytest.mark.asyncio
class TestSongFeaturesAccess:
    """Test Issue #4 & #5: Song.features scalar access and features dict structure"""
    
    async def test_acquisition_success_returns_features_dict(self):
        """Successful acquisition returns song with nested features dict."""
        from backend_v2.orchestration.agents import select_track_via_catalog
        from backend_v2.models.existing import Song, SongFeatures
        from backend_v2.models.track_intent import TrackIntent, TrackIntentStatus
        
        bundle = PreferenceBundle(
            user_id="test-user",
            session_id="test-session",
            context=ContextData(id="ctx-1", name="default", raw_text="test"),
            mood=MoodData(
                id="mood-1", name="Test", genres=["pop"],
                energy_target=0.5, valence_target=0.5, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(),
            history=HistoryData(),
            profile=UserProfileData(),
            agent_settings={},
            prompt_templates={},
        )
        
        state = {"session_id": "test-session"}
        db = AsyncMock()
        
        # Create mock song with features (scalar relationship, not list)
        mock_features = MagicMock(spec=SongFeatures)
        mock_features.energy = 0.8
        mock_features.valence = 0.7
        mock_features.tempo = 120.0
        mock_features.key = 5
        mock_features.mode = 1
        mock_features.danceability = 0.9
        mock_features.acousticness = 0.1
        mock_features.instrumentalness = 0.0
        
        mock_song = MagicMock(spec=Song)
        mock_song.uuid = "test-song-uuid"
        mock_song.title = "Test Track"
        mock_song.artist = "Test Artist"
        mock_song.local_path = "/path/to/song.mp3"
        mock_song.features = mock_features  # Scalar, not list
        
        # Mock catalog selection
        with patch("backend_v2.orchestration.agents.select_diverse_track") as mock_select:
            mock_track = CatalogTrack(
                title="Test Track",
                artist="Test Artist",
                provider="deezer",
                provider_id="12345"
            )
            mock_select.return_value = mock_track
            
            # Mock acquisition service
            with patch("backend_v2.orchestration.agents.get_acquisition_service") as mock_acq_service:
                mock_service = AsyncMock()
                mock_service.acquire.return_value = True
                mock_acq_service.return_value = mock_service
                
                # Mock TrackIntent creation
                with patch.object(TrackIntent, '__init__', return_value=None):
                    mock_intent = MagicMock(spec=TrackIntent)
                    mock_intent.id = "intent-1"
                    mock_intent.acquired_song_uuid = "test-song-uuid"
                    mock_intent.selection_rationale = "Test rationale"
                    mock_intent.artist = "Test Artist"
                    mock_intent.title = "Test Track"
                    
                    # Mock DB operations
                    db.add = MagicMock()
                    db.flush = AsyncMock()
                    
                    mock_result = AsyncMock()
                    mock_result.scalar_one_or_none.return_value = mock_song
                    db.execute = AsyncMock(return_value=mock_result)
                    
                    with patch("backend_v2.orchestration.agents.TrackIntent", return_value=mock_intent):
                        result = await select_track_via_catalog(
                            db=db,
                            bundle=bundle,
                            state=state,
                            prev_song=None,
                            history_ids=[],
                            use_intent_flow=True
                        )
                        
                        # Verify result has features dict
                        assert result is not None
                        assert "features" in result
                        assert isinstance(result["features"], dict)
                        
                        # Verify features are nested correctly
                        assert result["features"]["energy"] == 0.8
                        assert result["features"]["valence"] == 0.7
                        assert result["features"]["tempo"] == 120.0
                        assert result["features"]["key"] == 5
                        assert result["features"]["mode"] == 1
                        
                        # Verify top-level keys don't have individual feature values
                        assert "energy" not in result
                        assert "valence" not in result
                        assert "tempo" not in result
    
    async def test_selection_rationale_field_used(self):
        """Verify intent.selection_rationale field is used (not intent.rationale)."""
        from backend_v2.orchestration.agents import select_track_via_catalog
        from backend_v2.models.existing import Song, SongFeatures
        from backend_v2.models.track_intent import TrackIntent
        
        bundle = PreferenceBundle(
            user_id="test-user",
            session_id="test-session",
            context=ContextData(id="ctx-1", name="default", raw_text="test"),
            mood=MoodData(
                id="mood-1", name="Test", genres=["pop"],
                energy_target=0.5, valence_target=0.5, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(),
            history=HistoryData(),
            profile=UserProfileData(),
            agent_settings={},
            prompt_templates={},
        )
        
        state = {"session_id": "test-session"}
        db = AsyncMock()
        
        # Mock song
        mock_features = MagicMock(spec=SongFeatures)
        mock_features.energy = 0.8
        mock_features.valence = 0.7
        mock_features.tempo = 120.0
        mock_features.key = None
        mock_features.mode = None
        mock_features.danceability = None
        mock_features.acousticness = None
        mock_features.instrumentalness = None
        
        mock_song = MagicMock(spec=Song)
        mock_song.uuid = "test-uuid"
        mock_song.title = "Test"
        mock_song.artist = "Artist"
        mock_song.local_path = "/test.mp3"
        mock_song.features = mock_features
        
        with patch("backend_v2.orchestration.agents.select_diverse_track") as mock_select:
            mock_track = CatalogTrack(title="Test", artist="Artist", provider="deezer")
            mock_select.return_value = mock_track
            
            with patch("backend_v2.orchestration.agents.get_acquisition_service") as mock_acq:
                mock_service = AsyncMock()
                mock_service.acquire.return_value = True
                mock_acq.return_value = mock_service
                
                with patch.object(TrackIntent, '__init__', return_value=None):
                    mock_intent = MagicMock(spec=TrackIntent)
                    mock_intent.id = "intent-1"
                    mock_intent.acquired_song_uuid = "test-uuid"
                    mock_intent.selection_rationale = "Catalog diversity selection"  # Correct field
                    mock_intent.artist = "Artist"
                    mock_intent.title = "Test"
                    
                    db.add = MagicMock()
                    db.flush = AsyncMock()
                    mock_result = AsyncMock()
                    mock_result.scalar_one_or_none.return_value = mock_song
                    db.execute = AsyncMock(return_value=mock_result)
                    
                    with patch("backend_v2.orchestration.agents.TrackIntent", return_value=mock_intent):
                        result = await select_track_via_catalog(
                            db=db,
                            bundle=bundle,
                            state=state,
                            prev_song=None,
                            history_ids=[],
                            use_intent_flow=True
                        )
                        
                        # Verify rationale comes from selection_rationale field
                        assert result is not None
                        assert result["rationale"] == "Catalog diversity selection"

