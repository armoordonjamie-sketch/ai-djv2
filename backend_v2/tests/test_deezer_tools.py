import pytest
from httpx import AsyncClient, ASGITransport
from backend_v2.main import app

# Use a real secret for testing protected endpoints
# In real tests we might mock the verify_secret dependency
TEST_SECRET = "test-secret"

@pytest.fixture
def headers():
    return {"X-Onboard-Secret": "mock-secret"}  # Mock secret should work if we mock dependency or config

# Wait, better to write a check that hits the endpoints if possible, 
# but hitting real external APIs in tests is flaky.
# Ideally we mock the `httpx.AsyncClient` inside the router.

from unittest.mock import patch, MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_mood_search_endpoint():
    """Test mood-search endpoint logic with mocked Deezer response."""
    
    mock_response = {
        "data": [
            {
                "id": 123,
                "title": "Chill Track",
                "artist": {"name": "Chill Artist"},
                "duration": 180,
                "explicit_lyrics": False,
                "preview": "http://preview.url"
            }
        ]
    }
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp_obj = MagicMock()
        mock_resp_obj.status_code = 200
        mock_resp_obj.json.return_value = mock_response
        mock_get.return_value = mock_resp_obj
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # We need to bypass or satisfy auth
            # Let's assume we can set the secret header to what the app expects
            # Or simpler, patch _verify_secret
            
            with patch("backend_v2.api.deezer_tools._verify_secret"):
                response = await ac.post(
                    "/api/v1/deezer/mood-search",
                    json={"mood": "chill", "genres": ["lo-fi"]},
                    headers={"X-Onboard-Secret": "any"}
                )
                
    assert response.status_code == 200
    data = response.json()
    assert data["found"] is True
    assert len(data["tracks"]) == 1
    assert data["tracks"][0]["title"] == "Chill Track"


@pytest.mark.asyncio
async def test_era_search_endpoint():
    """Test era-search endpoint."""
    mock_response = {
        "data": [
            {
                "id": 456,
                "title": "90s Hit",
                "artist": {"name": "Retro Band"},
                "duration": 200,
                "explicit_lyrics": False,
                "preview": "http://preview.url"
            }
        ]
    }
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp_obj = MagicMock()
        mock_resp_obj.status_code = 200
        mock_resp_obj.json.return_value = mock_response
        mock_get.return_value = mock_resp_obj
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            with patch("backend_v2.api.deezer_tools._verify_secret"):
                response = await ac.post(
                    "/api/v1/deezer/era-search",
                    json={"era": "90s"},
                    headers={"X-Onboard-Secret": "any"}
                )
                
    assert response.status_code == 200
    data = response.json()
    assert data["found"] is True
    assert data["tracks"][0]["title"] == "90s Hit"


@pytest.mark.asyncio
async def test_vibe_check_endpoint():
    """Test vibe-check endpoint."""
    mock_response = {
        "data": [
            {
                "id": 789,
                "title": "Vibe Track",
                "artist": {"name": "Vibe Artist"},
                "duration": 150,
                "preview": "http://preview.url"
            }
        ]
    }
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp_obj = MagicMock()
        mock_resp_obj.status_code = 200
        mock_resp_obj.json.return_value = mock_response
        mock_get.return_value = mock_resp_obj
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            with patch("backend_v2.api.deezer_tools._verify_secret"):
                response = await ac.post(
                    "/api/v1/deezer/vibe-check",
                    json={"dimension": "energy"},
                    headers={"X-Onboard-Secret": "any"}
                )
                
    assert response.status_code == 200
    data = response.json()
    assert data["pair_name"] == "energy"
    assert "track_a" in data
    assert "track_b" in data


if __name__ == "__main__":
    import asyncio
    
    async def run_tests():
        print("Running mood search test...")
        await test_mood_search_endpoint()
        print("✅ Mood search passed")
        
        print("Running era search test...")
        await test_era_search_endpoint()
        print("✅ Era search passed")
        
        print("Running vibe check test...")
        await test_vibe_check_endpoint()
        print("✅ Vibe check passed")
        
    asyncio.run(run_tests())

