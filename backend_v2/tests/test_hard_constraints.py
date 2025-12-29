"""Tests for hard constraints and safe downloads.

Tests:
- Hard constraint filtering (tempo, energy, genre denylist)
- Download validation and denylist
- Search query format validation
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from backend_v2.services.preference_bundle import (
    check_hard_constraints,
    apply_hard_constraints,
)
from backend_v2.orchestration.agents import (
    _validate_download_query,
    _normalize_query,
)
from backend_v2.integrations.search_queries import (
    validate_query,
    validate_queries,
    ARTIST_TITLE_PATTERN,
)


# =============================================================================
# Hard Constraint Tests
# =============================================================================

class TestHardConstraints:
    """Tests for check_hard_constraints and apply_hard_constraints."""
    
    def test_slow_tempo_rejected(self):
        """Songs with tempo below threshold are rejected."""
        song = {
            "uuid": "test-1",
            "title": "Slow Song",
            "artist": "Test Artist",
            "features": {"tempo": 70, "energy": 0.5}
        }
        
        passes, reason = check_hard_constraints(song, min_tempo=90)
        
        assert not passes
        assert "tempo too low" in reason
    
    def test_acceptable_tempo_passes(self):
        """Songs with tempo at or above threshold pass."""
        song = {
            "uuid": "test-2",
            "title": "Fast Song",
            "artist": "Test Artist",
            "features": {"tempo": 120, "energy": 0.7}
        }
        
        passes, reason = check_hard_constraints(song, min_tempo=90)
        
        assert passes
        assert reason is None
    
    def test_low_energy_rejected(self):
        """Songs with energy below threshold are rejected."""
        song = {
            "uuid": "test-3",
            "title": "Low Energy",
            "artist": "Test Artist",
            "features": {"tempo": 120, "energy": 0.1}
        }
        
        passes, reason = check_hard_constraints(song, min_energy=0.3)
        
        assert not passes
        assert "energy too low" in reason
    
    def test_ballad_genre_rejected(self):
        """Songs with ballad genre are rejected."""
        song = {
            "uuid": "test-4",
            "title": "Love Ballad",
            "artist": "Test Artist",
            "features": {"tempo": 100, "energy": 0.5},
            "genres": ["ballad", "pop"],
        }
        
        passes, reason = check_hard_constraints(song)
        
        assert not passes
        assert "denied genre/tag" in reason
    
    def test_unknown_features_allowed_by_default(self):
        """Songs with no features pass when reject_unknown=False."""
        song = {
            "uuid": "test-5",
            "title": "Unknown Song",
            "artist": "Test Artist",
        }
        
        passes, reason = check_hard_constraints(song, reject_unknown=False)
        
        assert passes
    
    def test_unknown_features_rejected_when_strict(self):
        """Songs with no features rejected when reject_unknown=True."""
        song = {
            "uuid": "test-6",
            "title": "Unknown Song",
            "artist": "Test Artist",
        }
        
        passes, reason = check_hard_constraints(song, reject_unknown=True)
        
        assert not passes
        assert "unknown" in reason
    
    def test_apply_hard_constraints_filters_list(self):
        """apply_hard_constraints filters a list of songs."""
        songs = [
            {"uuid": "1", "features": {"tempo": 60, "energy": 0.8}},  # Too slow
            {"uuid": "2", "features": {"tempo": 120, "energy": 0.8}},  # OK
            {"uuid": "3", "features": {"tempo": 100, "energy": 0.1}},  # Low energy
            {"uuid": "4", "features": {"tempo": 110, "energy": 0.5}},  # OK
        ]
        
        mock_bundle = MagicMock()
        
        filtered = apply_hard_constraints(songs, mock_bundle, min_tempo=90, min_energy=0.3)
        
        assert len(filtered) == 2
        assert filtered[0]["uuid"] == "2"
        assert filtered[1]["uuid"] == "4"


# =============================================================================
# Download Validation Tests
# =============================================================================

class TestDownloadValidation:
    """Tests for download query validation."""
    
    def test_valid_query_passes(self):
        """Valid artist/title passes validation."""
        is_valid, reason = _validate_download_query("Queen", "Bohemian Rhapsody")
        
        assert is_valid
        assert reason is None
    
    def test_empty_artist_rejected(self):
        """Empty artist is rejected."""
        is_valid, reason = _validate_download_query("", "Some Title")
        
        assert not is_valid
        assert "empty artist" in reason
    
    def test_empty_title_rejected(self):
        """Empty title is rejected."""
        is_valid, reason = _validate_download_query("Artist", "")
        
        assert not is_valid
        assert "empty title" in reason
    
    def test_short_artist_rejected(self):
        """Single character artist is rejected."""
        is_valid, reason = _validate_download_query("A", "Some Title")
        
        assert not is_valid
        assert "artist too short" in reason
    
    def test_full_album_rejected(self):
        """Full album requests are rejected."""
        is_valid, reason = _validate_download_query("Pink Floyd", "Dark Side Full Album")
        
        assert not is_valid
        assert "denylist" in reason
    
    def test_live_set_rejected(self):
        """Live set requests are rejected."""
        is_valid, reason = _validate_download_query("DJ Snake", "Ultra 2023 Live Set")
        
        assert not is_valid
        assert "denylist" in reason
    
    def test_sped_up_rejected(self):
        """Sped up versions are rejected."""
        is_valid, reason = _validate_download_query("Taylor Swift", "Shake It Off Sped Up")
        
        assert not is_valid
        assert "denylist" in reason
    
    def test_nightcore_rejected(self):
        """Nightcore versions are rejected."""
        is_valid, reason = _validate_download_query("Various", "Song Nightcore")
        
        assert not is_valid
        assert "denylist" in reason
    
    def test_normalize_query(self):
        """Query normalization works correctly."""
        result = _normalize_query("  Queen  ", "  Bohemian Rhapsody  ")
        
        assert result == "queen - bohemian rhapsody"


# =============================================================================
# Search Query Format Tests
# =============================================================================

class TestSearchQueryFormat:
    """Tests for search query validation."""
    
    def test_valid_format_passes(self):
        """Valid 'Artist - Title' format passes."""
        result = validate_query("Queen - Bohemian Rhapsody")
        
        assert result == "Queen - Bohemian Rhapsody"
    
    def test_strips_leading_numbers(self):
        """Leading numbering is stripped."""
        result = validate_query("1. Queen - Radio Ga Ga")
        
        assert result == "Queen - Radio Ga Ga"
    
    def test_strips_bullets(self):
        """Bullets are stripped."""
        result = validate_query("- Queen - We Will Rock You")
        
        assert result == "Queen - We Will Rock You"
    
    def test_strips_quotes(self):
        """Quotes are stripped."""
        result = validate_query('"Daft Punk - Get Lucky"')
        
        assert result == "Daft Punk - Get Lucky"
    
    def test_rejects_single_artist(self):
        """Single artist name (no title) is rejected."""
        result = validate_query("Queen")
        
        assert result is None
    
    def test_rejects_genre(self):
        """Genre descriptions are rejected (no dash delimiter)."""
        result = validate_query("80s British synth-pop")
        
        assert result is None
    
    def test_rejects_denylist(self):
        """Denylist patterns are rejected."""
        result = validate_query("Various Artists - Best of 2023 Mix")
        
        assert result is None
    
    def test_validate_queries_deduplicates(self):
        """Duplicate queries are removed."""
        queries = [
            "Queen - Radio Ga Ga",
            "QUEEN - RADIO GA GA",
            "Daft Punk - Get Lucky",
        ]
        
        result = validate_queries(queries)
        
        assert len(result) == 2
    
    def test_validate_queries_filters_invalid(self):
        """Invalid queries are removed."""
        queries = [
            "Queen - Bohemian Rhapsody",  # Valid
            "Just a genre name",  # Invalid
            "Daft Punk",  # Invalid (no title)
            "ABBA - Dancing Queen",  # Valid
        ]
        
        result = validate_queries(queries)
        
        assert len(result) == 2
        assert result[0] == "Queen - Bohemian Rhapsody"
        assert result[1] == "ABBA - Dancing Queen"
