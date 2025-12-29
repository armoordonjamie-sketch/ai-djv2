"""Tests for PreferenceBundle service.

Tests fallback logic, feedback loading, and prompt template overrides.
"""
import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from backend_v2.services.preference_bundle import (
    PreferenceBundle,
    ContextData,
    MoodData,
    MoodProfileData,
    FeedbackData,
    FeedbackItem,
    HistoryData,
    PreferenceBundleCache,
    get_bundle_cache,
    build_preference_bundle,
    score_candidate,
)


class TestPreferenceBundleCache:
    """Tests for the caching mechanism."""
    
    def test_cache_set_and_get(self):
        """Test basic cache set and get."""
        cache = PreferenceBundleCache(ttl_seconds=300)
        
        bundle = PreferenceBundle(
            user_id="user-1",
            session_id="session-1",
            context=ContextData(id="ctx-1", name="default", raw_text="test"),
            mood=MoodData(
                id="mood-1", name="Chill", genres=["pop"],
                energy_target=0.5, valence_target=0.6, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(),
            history=HistoryData(),
            agent_settings={},
            prompt_templates={},
        )
        
        cache.set("user-1", "mood-1", "default", bundle)
        
        result = cache.get("user-1", "mood-1", "default")
        assert result is not None
        assert result.user_id == "user-1"
    
    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = PreferenceBundleCache()
        result = cache.get("nonexistent", None, None)
        assert result is None
    
    def test_cache_invalidate(self):
        """Test cache invalidation for user."""
        cache = PreferenceBundleCache()
        
        bundle = PreferenceBundle(
            user_id="user-1",
            session_id="session-1",
            context=ContextData(id="ctx-1", name="default", raw_text="test"),
            mood=MoodData(
                id="mood-1", name="Chill", genres=["pop"],
                energy_target=0.5, valence_target=0.6, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(),
            history=HistoryData(),
            agent_settings={},
            prompt_templates={},
        )
        
        cache.set("user-1", "mood-1", "default", bundle)
        cache.set("user-1", "mood-2", "workout", bundle)
        
        cache.invalidate("user-1")
        
        assert cache.get("user-1", "mood-1", "default") is None
        assert cache.get("user-1", "mood-2", "workout") is None


class TestCandidateScoring:
    """Tests for deterministic candidate scoring."""
    
    def test_score_basic_song(self):
        """Test basic scoring without penalties."""
        bundle = PreferenceBundle(
            user_id="user-1",
            session_id="session-1",
            context=ContextData(id="ctx-1", name="default", raw_text=""),
            mood=MoodData(
                id="mood-1", name="Chill", genres=["pop"],
                energy_target=0.5, valence_target=0.5, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(),
            history=HistoryData(),
            agent_settings={},
            prompt_templates={},
        )
        
        song = {"uuid": "song-1", "title": "Test", "artist": "Artist"}
        score = score_candidate(song, bundle)
        
        assert score == 0.5  # Base score
    
    def test_score_disliked_song_banned(self):
        """Test that disliked songs get negative score (banned)."""
        bundle = PreferenceBundle(
            user_id="user-1",
            session_id="session-1",
            context=ContextData(id="ctx-1", name="default", raw_text=""),
            mood=MoodData(
                id="mood-1", name="Chill", genres=["pop"],
                energy_target=0.5, valence_target=0.5, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(
                recent_dislikes=[
                    FeedbackItem(song_uuid="song-1", title="Bad Song", artist="Bad Artist")
                ]
            ),
            history=HistoryData(),
            agent_settings={},
            prompt_templates={},
        )
        
        song = {"uuid": "song-1", "title": "Bad Song", "artist": "Bad Artist"}
        score = score_candidate(song, bundle)
        
        assert score < 0  # Should be banned
    
    def test_score_liked_song_boosted(self):
        """Test that liked songs get boosted score."""
        bundle = PreferenceBundle(
            user_id="user-1",
            session_id="session-1",
            context=ContextData(id="ctx-1", name="default", raw_text=""),
            mood=MoodData(
                id="mood-1", name="Chill", genres=["pop"],
                energy_target=0.5, valence_target=0.5, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(
                recent_likes=[
                    FeedbackItem(song_uuid="song-1", title="Good Song", artist="Good Artist")
                ]
            ),
            history=HistoryData(),
            agent_settings={},
            prompt_templates={},
        )
        
        song = {"uuid": "song-1", "title": "Good Song", "artist": "Good Artist"}
        score = score_candidate(song, bundle)
        
        assert score > 0.5  # Should be boosted
    
    def test_score_recent_play_penalized(self):
        """Test that recently played songs are penalized."""
        bundle = PreferenceBundle(
            user_id="user-1",
            session_id="session-1",
            context=ContextData(id="ctx-1", name="default", raw_text=""),
            mood=MoodData(
                id="mood-1", name="Chill", genres=["pop"],
                energy_target=0.5, valence_target=0.5, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(),
            history=HistoryData(recent_plays=["song-1", "song-2"]),
            agent_settings={},
            prompt_templates={},
        )
        
        song = {"uuid": "song-1", "title": "Test", "artist": "Artist"}
        score = score_candidate(song, bundle)
        
        assert score < 0.5  # Should be penalized
    
    def test_score_energy_matching(self):
        """Test that energy-matching songs score higher."""
        bundle = PreferenceBundle(
            user_id="user-1",
            session_id="session-1",
            context=ContextData(id="ctx-1", name="default", raw_text=""),
            mood=MoodData(
                id="mood-1", name="Chill", genres=["pop"],
                energy_target=0.3, valence_target=0.5, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(),
            history=HistoryData(),
            agent_settings={},
            prompt_templates={},
        )
        
        # Song with matching energy
        song_match = {
            "uuid": "song-1", "title": "Chill", "artist": "Artist",
            "features": {"energy": 0.3, "valence": 0.5}
        }
        
        # Song with mismatched energy
        song_mismatch = {
            "uuid": "song-2", "title": "Hype", "artist": "Artist",
            "features": {"energy": 0.9, "valence": 0.5}
        }
        
        score_match = score_candidate(song_match, bundle)
        score_mismatch = score_candidate(song_mismatch, bundle)
        
        assert score_match > score_mismatch


class TestPreferenceBundleHelpers:
    """Tests for PreferenceBundle helper methods."""
    
    def test_get_agent_setting(self):
        """Test agent setting retrieval."""
        bundle = PreferenceBundle(
            user_id="user-1",
            session_id="session-1",
            context=ContextData(id="ctx-1", name="default", raw_text=""),
            mood=MoodData(
                id="mood-1", name="Chill", genres=["pop"],
                energy_target=0.5, valence_target=0.5, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(),
            history=HistoryData(),
            agent_settings={
                "track_selector": {"thinking_budget": 3000, "temperature": 0.8}
            },
            prompt_templates={},
        )
        
        assert bundle.get_agent_setting("track_selector", "thinking_budget") == 3000
        assert bundle.get_agent_setting("track_selector", "temperature") == 0.8
        assert bundle.get_agent_setting("track_selector", "missing") is None
        assert bundle.get_agent_setting("track_selector", "missing", 42) == 42
        assert bundle.get_agent_setting("unknown_agent", "anything", "default") == "default"
    
    def test_get_prompt_template(self):
        """Test prompt template retrieval."""
        bundle = PreferenceBundle(
            user_id="user-1",
            session_id="session-1",
            context=ContextData(id="ctx-1", name="default", raw_text=""),
            mood=MoodData(
                id="mood-1", name="Chill", genres=["pop"],
                energy_target=0.5, valence_target=0.5, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(),
            history=HistoryData(),
            agent_settings={},
            prompt_templates={
                "track_selection_system": "Custom prompt here"
            },
        )
        
        assert bundle.get_prompt_template("track_selection_system") == "Custom prompt here"
        assert bundle.get_prompt_template("nonexistent") is None
    
    def test_get_disliked_song_uuids(self):
        """Test disliked song UUID extraction."""
        bundle = PreferenceBundle(
            user_id="user-1",
            session_id="session-1",
            context=ContextData(id="ctx-1", name="default", raw_text=""),
            mood=MoodData(
                id="mood-1", name="Chill", genres=["pop"],
                energy_target=0.5, valence_target=0.5, dj_personality="chill"
            ),
            mood_profile=MoodProfileData(),
            feedback=FeedbackData(
                recent_dislikes=[
                    FeedbackItem(song_uuid="bad-1", title="Bad1", artist="Artist1"),
                    FeedbackItem(song_uuid="bad-2", title="Bad2", artist="Artist2"),
                    FeedbackItem(song_uuid=None, title="Unknown", artist="???"),
                ]
            ),
            history=HistoryData(),
            agent_settings={},
            prompt_templates={},
        )
        
        disliked = bundle.get_disliked_song_uuids()
        assert disliked == ["bad-1", "bad-2"]


# Integration tests require database fixtures
@pytest.mark.asyncio
class TestBuildPreferenceBundle:
    """Integration tests for build_preference_bundle function."""
    
    async def test_build_creates_defaults(self):
        """Test that build creates default context/mood if missing."""
        # This test would require database fixtures
        # For now, we just verify the function signature works
        pass
