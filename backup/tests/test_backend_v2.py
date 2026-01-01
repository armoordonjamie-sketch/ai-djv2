"""Tests for AI DJ Backend V2 features."""
import pytest
import asyncio
import re
from unittest.mock import Mock, AsyncMock, patch


class TestTTSSanitization:
    """Test that TTS output doesn't contain technical audio terms."""
    
    def test_sanitize_bpm_mentions(self):
        """Test removal of BPM mentions."""
        from backend_v2.integrations.openrouter import OpenRouterClient
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
        from backend_v2.integrations.openrouter import OpenRouterClient
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
        from backend_v2.integrations.openrouter import OpenRouterClient
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
        from backend_v2.integrations.openrouter import OpenRouterClient
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
        from backend_v2.integrations.metadata.musicbrainz import MusicBrainzClient
        client = MusicBrainzClient()
        
        assert "musicbrainz.org" in client.base_url
        assert "User-Agent" in client.headers
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test that rate limiting delays requests."""
        from backend_v2.integrations.metadata.musicbrainz import MusicBrainzClient
        
        client = MusicBrainzClient()
        assert client.rate_limiter.min_interval > 0

    @pytest.mark.asyncio
    async def test_cache_storage_and_retrieval(self):
        """Test caching works correctly."""
        from backend_v2.integrations.metadata.musicbrainz import MusicBrainzClient
        client = MusicBrainzClient()
        
        test_key = "test_cache_key"
        test_data = [{"name": "Test Song", "artist": "Test Artist"}]
        
        # Store in cache
        client._set_cached(test_key, test_data)
        
        # Retrieve from cache
        cached = client._get_cached(test_key)
        
        assert cached == test_data


class TestListenBrainzClient:
    """Tests for ListenBrainz API client."""
    
    @pytest.mark.asyncio
    async def test_client_initialization(self, monkeypatch):
        """Test client initializes correctly."""
        from backend_v2.integrations.metadata import listenbrainz

        monkeypatch.setattr(listenbrainz, "LISTENBRAINZ_USER_TOKEN", "test-token")
        client = listenbrainz.ListenBrainzClient()

        assert "listenbrainz.org" in client.base_url
        assert client.headers["Authorization"] == "Token test-token"

    @pytest.mark.asyncio
    async def test_request_returns_payload(self, monkeypatch):
        """Test request path returns parsed JSON."""
        from backend_v2.integrations.metadata import listenbrainz

        monkeypatch.setattr(listenbrainz, "LISTENBRAINZ_USER_TOKEN", "test-token")
        client = listenbrainz.ListenBrainzClient()

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"ok": True}

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", new=AsyncMock(return_value=mock_http)):
            result = await client._request("user/test/listens", params={"count": 1})

        assert result == {"ok": True}


class TestQueueBackpressure:
    """Tests for segment queue backpressure."""
    
    def test_queue_has_maxsize(self):
        """Test that DJLoop creates bounded queue."""
        from backend_v2.orchestration.loop import DJLoop
        loop = DJLoop(user_id="test-user", session_id="test-session")
        
        # Check the maxsize is set
        assert loop.segment_queue.maxsize == 3


# Run with: pytest backend/tests/test_backend_v2.py -v
