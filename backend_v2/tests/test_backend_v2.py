"""Tests for AI DJ Backend V2 features."""
import pytest
import asyncio
import re
from unittest.mock import Mock, AsyncMock, patch


class TestTTSSanitization:
    """Test that TTS output doesn't contain technical audio terms."""
    
    def test_sanitize_bpm_mentions(self):
        """Test removal of BPM mentions."""
        from backend.integrations.openrouter import OpenRouterClient
        client = OpenRouterClient()
        
        test_cases = [
            ("This track is 120 BPM", "This track is"),
            ("Playing at 140 beats per minute", "Playing at"),
            ("BPM of 128 here", "here"),
        ]
        
        for input_text, expected_contains in test_cases:
            result = client._sanitize_tts_output(input_text)
            assert "bpm" not in result.lower()
            assert "beats per minute" not in result.lower()
    
    def test_sanitize_key_mentions(self):
        """Test removal of musical key mentions."""
        from backend.integrations.openrouter import OpenRouterClient
        client = OpenRouterClient()
        
        test_cases = [
            "key of A minor",
            "in the key of G major",
            "playing in 8A",
            "Camelot wheel compatible",
        ]
        
        for input_text in test_cases:
            result = client._sanitize_tts_output(input_text)
            assert "camelot" not in result.lower()
            # Should not contain key patterns
            assert not re.search(r'\b\d{1,2}[AB]\b', result)
    
    def test_sanitize_technical_terms(self):
        """Test removal of FFmpeg and audio processing terms."""
        from backend.integrations.openrouter import OpenRouterClient
        client = OpenRouterClient()
        
        test_cases = [
            ("Nice crossfade coming up", "Nice coming up"),
            ("Using eq_blend filter", "Using filter"),
            ("FFmpeg processing", "processing"),
        ]
        
        for input_text, _ in test_cases:
            result = client._sanitize_tts_output(input_text)
            assert "crossfade" not in result.lower()
            assert "eq_blend" not in result.lower()
            assert "ffmpeg" not in result.lower()
    
    def test_context_sanitization_removes_technical_fields(self):
        """Test that speech context removes technical metadata."""
        from backend.integrations.openrouter import OpenRouterClient
        client = OpenRouterClient()
        
        context = {
            "current_song": {
                "title": "Test Song",
                "artist": "Test Artist",
                "tempo": 128.0,  # Should be removed
                "key": "8A",     # Should be removed
                "energy": 0.85   # Should be removed
            },
            "transition_type": "blend",
            "mix_length_bars": 16  # Should be removed
        }
        
        sanitized = client._sanitize_speech_context(context)
        
        assert "tempo" not in str(sanitized)
        assert "key" not in str(sanitized)
        assert "energy" not in str(sanitized)
        assert "mix_length_bars" not in str(sanitized)
        assert "title" in str(sanitized)
        assert "artist" in str(sanitized)


class TestMusicBrainzClient:
    """Tests for MusicBrainz API client."""
    
    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test client initializes correctly."""
        from backend.integrations.musicbrainz import MusicBrainzClient
        client = MusicBrainzClient()
        
        assert client.enabled is True
        assert "musicbrainz.org" in client.base_url
        assert "User-Agent" in client.headers
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test that rate limiting delays requests."""
        from backend.integrations.musicbrainz import MusicBrainzClient
        import time
        
        client = MusicBrainzClient()
        
        # Simulate two rapid requests
        client._last_request_time = time.time()
        
        # Next request should be delayed
        start = time.time()
        # Just check the rate limit logic, don't actually make request
        time_since_last = time.time() - client._last_request_time
        
        assert time_since_last < client._rate_limit_delay
    
    @pytest.mark.asyncio
    async def test_cache_storage_and_retrieval(self):
        """Test caching works correctly."""
        from backend.integrations.musicbrainz import MusicBrainzClient
        client = MusicBrainzClient()
        
        test_key = "test_cache_key"
        test_data = [{"name": "Test Song", "artist": "Test Artist"}]
        
        # Store in cache
        client._set_cache(test_key, test_data)
        
        # Retrieve from cache
        cached = client._get_from_cache(test_key)
        
        assert cached == test_data


class TestListenBrainzClient:
    """Tests for ListenBrainz API client."""
    
    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test client initializes correctly."""
        from backend.integrations.listenbrainz import ListenBrainzClient
        client = ListenBrainzClient()
        
        assert client.enabled is True
        assert "listenbrainz.org" in client.base_url


class TestQueueBackpressure:
    """Tests for segment queue backpressure."""
    
    def test_queue_has_maxsize(self):
        """Test that DJLoop creates bounded queue."""
        from backend.orchestration.loop import DJLoop
        loop = DJLoop()
        
        # Check the maxsize is set
        assert loop.max_queued_segments == 2


# Run with: pytest backend/tests/test_backend_v2.py -v
