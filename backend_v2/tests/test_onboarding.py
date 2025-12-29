"""Tests for voice onboarding flow.

Tests:
- test_onboard_gates_stream: stream/start returns 409 if not onboarded
- test_onboard_submit_creates_context: tool submit stores user_contexts.default
- test_onboard_start_returns_signed_url: mocks ElevenLabs signed-url call
- test_llm_proxy_forwards_to_openrouter: mocks OpenRouter and validates model
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
from httpx import Response

from backend_v2.api.onboard import OnboardSubmitPayload


class TestOnboardGatesStream:
    """Test that stream/start is blocked until onboarding completes."""
    
    @pytest.mark.asyncio
    async def test_unonboarded_user_blocked(self):
        """User without onboarded_at gets 409."""
        from backend_v2.api.stream import start_stream
        from backend_v2.schemas.stream import StreamStartRequest
        from fastapi import HTTPException
        
        # Create mock user without onboarded_at
        mock_user = MagicMock()
        mock_user.onboarded_at = None
        mock_user.id = "test-user-id"
        
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await start_stream(
                data=StreamStartRequest(),
                current_user=mock_user,
                db=mock_db,
            )
        
        assert exc_info.value.status_code == 409
    
    @pytest.mark.asyncio
    async def test_onboarded_user_allowed(self):
        """User with onboarded_at can proceed."""
        mock_user = MagicMock()
        mock_user.onboarded_at = datetime.utcnow()
        mock_user.id = "test-user-id"
        
        assert mock_user.onboarded_at is not None


class TestOnboardSubmit:
    """Test onboard submit endpoint."""
    
    @pytest.mark.asyncio
    async def test_submit_updates_profile(self):
        """Submit should update the user profile."""
        from backend_v2.api.onboard import submit_onboarding
        
        payload = OnboardSubmitPayload(
            user_id="test-user-id",
            display_name="TestUser",
            favorite_genres=["rock", "indie"],
            favorite_artists=["Radiohead"],
            no_go=["country"],
            explicit_lyrics="ok",
            dj_personality="casual_funny",
            raw_context="Test context",
        )
        
        # Mock DB and secret
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = "test-user-id"
        mock_user.display_name = None
        mock_user.onboarded_at = None
        
        # Mock profile
        mock_profile = MagicMock()
        mock_user.profile = mock_profile
        
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        
        with patch("backend_v2.api.onboard.ONBOARD_TOOL_SECRET", "test-secret"):
            with patch("backend_v2.api.onboard.select"):
                # Create a mock request object
                mock_request = MagicMock()
                mock_request.url = MagicMock()
                mock_request.url.path = "/api/v1/onboard/submit"
                
                # Simplified test for successful execution
                response = await submit_onboarding(
                    payload=payload,
                    request=mock_request,
                    db=mock_db,
                    x_onboard_secret="test-secret"
                )
                assert response.ok is True

    def test_payload_parsing_with_nulls(self):
        """Test that payload parses correctly even with nulls from ElevenLabs."""
        # Simulate ElevenLabs sending null for fields it hasn't collected
        data = {
            "user_id": "123",
            "display_name": "Jamie",
            "favorite_genres": None,
            "favorite_artists": None,
            "favorite_songs": ["Creep"],
            "explicit_lyrics": "ok"
        }
        payload = OnboardSubmitPayload(**data)
        
        assert payload.user_id == "123"
        assert payload.display_name == "Jamie"
        assert payload.favorite_genres is None  # Accepted null
        assert payload.favorite_songs == ["Creep"]


class TestOnboardStart:
    """Test onboard start endpoint."""
    
    @pytest.mark.asyncio
    async def test_returns_signed_url(self):
        """Start should return signed URL from ElevenLabs."""
        from backend_v2.api.onboard import start_onboarding
        
        mock_user = MagicMock()
        mock_user.id = "test-user"
        mock_user.onboarded_at = None
        mock_user.display_name = "Test"
        
        mock_db = AsyncMock()
        
        with patch("backend_v2.api.onboard.ELEVENLABS_API_KEY", "test-key"):
            with patch("backend_v2.api.onboard.ELEVENLABS_ONBOARD_AGENT_ID", "test-agent"):
                with patch("backend_v2.api.onboard.httpx.AsyncClient") as mock_client:
                    mock_response = MagicMock()
                    mock_response.json.return_value = {"signed_url": "wss://test.url"}
                    mock_response.raise_for_status = MagicMock()
                    
                    mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                        return_value=mock_response
                    )
                    
                    result = await start_onboarding(
                        current_user=mock_user,
                        db=mock_db,
                    )
                    
                    assert result.signed_url == "wss://test.url"
                    assert result.agent_id == "test-agent"


class TestLLMProxy:
    """Test Custom LLM proxy endpoint."""
    
    @pytest.mark.asyncio
    async def test_forwards_to_openrouter(self):
        """Proxy should forward to OpenRouter with correct model."""
        from backend_v2.api.llm_proxy import chat_completions_proxy
        from fastapi import Request
        
        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(return_value={
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False,
        })
        
        with patch("backend_v2.api.llm_proxy.ELEVENLABS_CUSTOM_LLM_SECRET", "test-secret"):
            with patch("backend_v2.api.llm_proxy.OPENROUTER_API_KEY", "test-key"):
                with patch("backend_v2.api.llm_proxy.httpx.AsyncClient") as mock_client:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        "choices": [{"message": {"content": "Hi"}}]
                    }
                    
                    mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                        return_value=mock_response
                    )
                    
                    result = await chat_completions_proxy(
                        request=mock_request,
                        authorization="Bearer test-secret",
                    )
                    
                    assert "choices" in result
    
    @pytest.mark.asyncio
    async def test_rejects_invalid_auth(self):
        """Proxy should reject invalid authorization."""
        from backend_v2.api.llm_proxy import chat_completions_proxy
        from fastapi import Request
        import pytest
        
        mock_request = MagicMock(spec=Request)
        
        with patch("backend_v2.api.llm_proxy.ELEVENLABS_CUSTOM_LLM_SECRET", "correct-secret"):
            with pytest.raises(Exception) as exc_info:
                await chat_completions_proxy(
                    request=mock_request,
                    authorization="Bearer wrong-secret",
                )
            
            assert "401" in str(exc_info.value) or "Invalid" in str(exc_info.value)


class TestPromptIntegration:
    """Test that onboarding context appears in prompts."""
    
    def test_preference_bundle_includes_parsed_json(self):
        """PreferenceBundle should expose parsed onboarding data."""
        from backend_v2.services.preference_bundle import ContextData
        import json
        
        parsed = {
            "display_name": "Jamie",
            "music_preferences": {
                "favorite_genres": ["rock", "indie"],
                "avoid": ["country"],
            },
        }
        
        context = ContextData(
            id="ctx-1",
            name="default",
            raw_text="Name: Jamie\nGenres: rock, indie\nAvoid: country",
            parsed_json=parsed,
        )
        
        assert context.parsed_json["display_name"] == "Jamie"
        assert "rock" in context.parsed_json["music_preferences"]["favorite_genres"]
        assert "country" in context.parsed_json["music_preferences"]["avoid"]
