"""Tests for Deezer API client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from backend_v2.integrations.deezer import DeezerClient, get_deezer_client


class TestDeezerClient:
    """Test Deezer API client."""
    
    @pytest.fixture
    def client(self):
        """Create a fresh client for each test."""
        return DeezerClient()
    
    @pytest.mark.asyncio
    async def test_search_artist_found(self, client):
        """Test artist search returns expected format."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{
                "id": 1234,
                "name": "Taylor Swift",
                "picture_medium": "https://pic.example.com/medium.jpg",
                "nb_fan": 5000000,
                "nb_album": 10,
                "link": "https://deezer.com/artist/1234"
            }]
        }
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http
            
            result = await client.search_artist("Taylor Swift")
            
            assert result is not None
            assert result["id"] == 1234
            assert result["name"] == "Taylor Swift"
            assert result["nb_fan"] == 5000000
    
    @pytest.mark.asyncio
    async def test_search_artist_not_found(self, client):
        """Test artist search returns None when no results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http
            
            result = await client.search_artist("NonexistentArtist123456")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_get_artist_top_tracks(self, client):
        """Test getting artist top tracks."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": 111,
                    "title": "Shake It Off",
                    "title_short": "Shake It Off",
                    "duration": 219,
                    "rank": 1000000,
                    "preview": "https://preview.example.com/shake.mp3",
                    "explicit_lyrics": False,
                    "artist": {"name": "Taylor Swift"},
                    "album": {"title": "1989", "cover_medium": "https://cover.example.com"}
                },
                {
                    "id": 222,
                    "title": "Blank Space",
                    "title_short": "Blank Space",
                    "duration": 231,
                    "rank": 900000,
                    "preview": "https://preview.example.com/blank.mp3",
                    "explicit_lyrics": False,
                    "artist": {"name": "Taylor Swift"},
                    "album": {"title": "1989", "cover_medium": "https://cover.example.com"}
                }
            ]
        }
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http
            
            tracks = await client.get_artist_top_tracks(1234, limit=5)
            
            assert len(tracks) == 2
            assert tracks[0]["title"] == "Shake It Off"
            assert tracks[0]["preview"] == "https://preview.example.com/shake.mp3"
            assert tracks[1]["title"] == "Blank Space"
    
    @pytest.mark.asyncio
    async def test_search_tracks_with_query(self, client):
        """Test track search with query."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{
                "id": 333,
                "title": "Cruel Summer",
                "title_short": "Cruel Summer",
                "duration": 178,
                "rank": 800000,
                "preview": "https://preview.example.com/cruel.mp3",
                "explicit_lyrics": False,
                "artist": {"id": 1234, "name": "Taylor Swift"},
                "album": {"id": 5678, "title": "Lover", "cover_medium": "https://cover.example.com"}
            }]
        }
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http
            
            tracks = await client.search_tracks('artist:"Taylor Swift" track:"Cruel Summer"')
            
            assert len(tracks) == 1
            assert tracks[0]["title"] == "Cruel Summer"
            assert tracks[0]["artist"]["name"] == "Taylor Swift"
    
    def test_caching_works(self, client):
        """Test that cache stores and retrieves values."""
        key = client._cache_key("test", foo="bar")
        
        # Initially empty
        assert client._get_cached(key) is None
        
        # Store value
        client._set_cached(key, {"result": "cached"})
        
        # Retrieve value
        cached = client._get_cached(key)
        assert cached == {"result": "cached"}
    
    def test_cache_expiry(self, client):
        """Test that expired cache entries are not returned."""
        key = client._cache_key("test", foo="baz")
        
        # Store with expired timestamp
        client._cache[key] = ({"old": "data"}, datetime.utcnow() - timedelta(days=2))
        
        # Should not return expired entry
        assert client._get_cached(key) is None


class TestDeezerSingleton:
    """Test singleton pattern."""
    
    def test_get_deezer_client_returns_same_instance(self):
        """get_deezer_client should return the same instance."""
        # Reset singleton for test
        import backend_v2.integrations.deezer as deezer_module
        deezer_module._client = None
        
        client1 = get_deezer_client()
        client2 = get_deezer_client()
        
        assert client1 is client2
