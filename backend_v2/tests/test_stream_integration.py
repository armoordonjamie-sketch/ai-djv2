"""Integration tests for stream lifecycle and WebSocket.

Run with: pytest backend_v2/tests/test_stream_integration.py -v
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


class TestWebSocketEventEmitter:
    """Test that WebSocket events are properly scoped per user."""
    
    @pytest.mark.asyncio
    async def test_emitter_isolates_users(self):
        """Test that UserEventEmitter only sends to correct user."""
        from backend_v2.orchestration.events import UserEventEmitter
        
        emitter = UserEventEmitter()
        
        # Create mock websockets for two users
        ws_user_a = AsyncMock()
        ws_user_b = AsyncMock()
        
        # Register connections
        await emitter.connect("user-a", ws_user_a)
        await emitter.connect("user-b", ws_user_b)
        
        # Emit to user A only
        await emitter.emit_to_user("user-a", "test_event", {"data": "for_a"})
        
        # User A should receive, user B should not
        ws_user_a.send_text.assert_called_once()
        ws_user_b.send_text.assert_not_called()
        
        # Verify message format
        import json
        sent_message = json.loads(ws_user_a.send_text.call_args[0][0])
        assert sent_message["v"] == 2
        assert sent_message["type"] == "test_event"
        assert sent_message["data"]["data"] == "for_a"
    
    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self):
        """Test that disconnect removes the connection."""
        from backend_v2.orchestration.events import UserEventEmitter
        
        emitter = UserEventEmitter()
        ws = AsyncMock()
        
        await emitter.connect("user-test", ws)
        assert emitter.get_user_connection_count("user-test") == 1
        
        await emitter.disconnect("user-test", ws)
        assert emitter.get_user_connection_count("user-test") == 0
    
    @pytest.mark.asyncio
    async def test_multiple_connections_per_user(self):
        """Test user can have multiple connections (tabs)."""
        from backend_v2.orchestration.events import UserEventEmitter
        
        emitter = UserEventEmitter()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        
        await emitter.connect("user-multi", ws1)
        await emitter.connect("user-multi", ws2)
        
        assert emitter.get_user_connection_count("user-multi") == 2
        
        # Emit should go to both
        await emitter.emit_to_user("user-multi", "multi_test", {})
        
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()


class TestEventFormat:
    """Test event message format."""
    
    @pytest.mark.asyncio
    async def test_now_playing_event_format(self):
        """Test now_playing event has correct structure."""
        from backend_v2.orchestration.events import UserEventEmitter
        import json
        
        emitter = UserEventEmitter()
        ws = AsyncMock()
        
        await emitter.connect("user-np", ws)
        await emitter.emit_now_playing(
            user_id="user-np",
            song_uuid="test-uuid",
            title="Test Song",
            artist="Test Artist",
            artwork_url="https://example.com/art.jpg"
        )
        
        ws.send_text.assert_called_once()
        event = json.loads(ws.send_text.call_args[0][0])
        
        assert event["v"] == 2
        assert event["type"] == "now_playing"
        assert event["data"]["song_uuid"] == "test-uuid"
        assert event["data"]["title"] == "Test Song"
        assert event["data"]["artist"] == "Test Artist"
        assert event["data"]["artwork_url"] == "https://example.com/art.jpg"
        assert "ts" in event


class TestPipelineCreation:
    """Test pipeline creation logic (without actually spawning FFmpeg)."""
    
    @pytest.mark.asyncio
    async def test_pipeline_state_initialization(self):
        """Test UserRadioPipeline initializes with correct state."""
        from backend_v2.streaming.pipeline import UserRadioPipeline
        
        pipeline = UserRadioPipeline(
            user_id="test-user",
            session_id="test-session"
        )
        
        assert pipeline.user_id == "test-user"
        assert pipeline.session_id == "test-session"
        assert pipeline.is_running is False
        assert pipeline.now_playing is None
        
    @pytest.mark.asyncio
    async def test_pipeline_get_state(self):
        """Test pipeline state dict includes expected fields."""
        from backend_v2.streaming.pipeline import UserRadioPipeline
        
        pipeline = UserRadioPipeline(
            user_id="test-user-2",
            session_id="test-session-2"
        )
        
        state = pipeline.get_state()
        
        assert state["user_id"] == "test-user-2"
        assert state["session_id"] == "test-session-2"
        assert state["is_running"] is False
        assert "created_at" in state
        assert "last_activity" in state


class TestStreamAPISchemas:
    """Test stream API request/response schemas."""
    
    def test_start_request_schema(self):
        """Test StreamStartRequest validation."""
        from backend_v2.schemas.stream import StreamStartRequest
        
        # Empty request is valid
        req = StreamStartRequest()
        assert req.mood_id is None
        assert req.context_name is None
        
        # With optional fields
        req = StreamStartRequest(mood_id="mood-123", context_name="my-context")
        assert req.mood_id == "mood-123"
        assert req.context_name == "my-context"
    
    def test_start_response_schema(self):
        """Test StreamStartResponse has required fields."""
        from backend_v2.schemas.stream import StreamStartResponse
        
        resp = StreamStartResponse(
            session_id="session-123",
            stream_url="/api/v1/stream",
            ws_url="/api/v1/ws"
        )
        
        assert resp.session_id == "session-123"
        assert resp.stream_url == "/api/v1/stream"
        assert resp.ws_url == "/api/v1/ws"


# Run with: pytest backend_v2/tests/test_stream_integration.py -v
