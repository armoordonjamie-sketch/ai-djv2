"""WebSocket API endpoint with cookie-first authentication.

Provides real-time events to authenticated users:
- now_playing: Current song changes
- segment_ready: New audio segment available
- decision_trace: AI decisions (for transparency)
- dj_says: DJ speech scripts
- stream_status: Stream lifecycle events

Security:
- Cookie-first authentication (HttpOnly access_token cookie)
- Query token fallback ONLY if WS_ALLOW_QUERY_TOKEN=true (dev mode)
- Per-user event scoping (users cannot see other users' events)
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend_v2.db.session import get_async_session
from backend_v2.auth.dependencies import get_current_user_ws
from backend_v2.config import WS_ALLOW_QUERY_TOKEN
from backend_v2.orchestration.events import get_event_emitter

logger = logging.getLogger("ai-dj.ws")

router = APIRouter()


class WSMessage(BaseModel):
    """Inbound WebSocket message format."""
    type: str
    data: dict = {}


@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, alias="token"),
):
    """WebSocket endpoint for real-time events.
    
    Authentication:
    1. HttpOnly cookie (preferred) - access_token cookie
    2. Query parameter (dev only) - ?token=xxx if WS_ALLOW_QUERY_TOKEN=true
    
    Event Format (server -> client):
    {
        "v": 1,
        "type": "now_playing",
        "data": {...},
        "ts": "2024-01-01T00:00:00Z"
    }
    
    Message Format (client -> server):
    {
        "type": "ping",
        "data": {}
    }
    """
    # Accept the connection first (required for cookie access)
    await websocket.accept()
    
    # Authenticate
    try:
        # Get database session
        async for db in get_async_session():
            user = await get_current_user_ws(
                websocket=websocket,
                db=db,
                token_param=token if WS_ALLOW_QUERY_TOKEN else None
            )
            break
    except Exception as e:
        logger.warning(f"WS auth failed: {e}")
        await websocket.close(code=1008, reason="Authentication required")
        return
        
    user_id = user.id
    emitter = get_event_emitter()
    
    # Register connection
    await emitter.connect(user_id, websocket)
    
    # Send welcome message
    await websocket.send_json({
        "v": 1,
        "type": "connected",
        "data": {
            "user_id": user_id,
            "message": "Connected to AI DJ"
        }
    })
    
    # Replay recent status events for reconnect UX
    recent_events = emitter.get_events_since(user_id, last_event_id=None)
    if recent_events:
        # Only send the last 5 events to avoid flooding
        for event in recent_events[-5:]:
            try:
                await websocket.send_json({
                    "v": 2,
                    "type": "status",
                    "data": event.model_dump(mode="json")
                })
            except Exception:
                break  # Stop if client disconnects
    
    try:
        while True:
            try:
                # Receive message with timeout for keepalive
                raw_message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0
                )
                
                # Parse and validate
                try:
                    data = json.loads(raw_message)
                    message = WSMessage(**data)
                except (json.JSONDecodeError, ValidationError) as e:
                    await websocket.send_json({
                        "v": 1,
                        "type": "error",
                        "data": {"message": f"Invalid message format: {e}"}
                    })
                    continue
                    
                # Handle message types
                if message.type == "ping":
                    await websocket.send_json({
                        "v": 1,
                        "type": "pong",
                        "data": {}
                    })
                elif message.type == "get_status":
                    # Return current stream status
                    from backend_v2.streaming.pipeline import get_user_pipeline
                    pipeline = await get_user_pipeline(user_id, "", create_if_missing=False)
                    await websocket.send_json({
                        "v": 1,
                        "type": "status",
                        "data": {
                            "streaming": pipeline is not None and pipeline.is_running
                        }
                    })
                else:
                    await websocket.send_json({
                        "v": 1,
                        "type": "error",
                        "data": {"message": f"Unknown message type: {message.type}"}
                    })
                    
            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await websocket.send_json({
                        "v": 1,
                        "type": "ping",
                        "data": {}
                    })
                except:
                    break
                    
    except WebSocketDisconnect:
        logger.debug(f"WS disconnected normally: user {user_id}")
    except Exception as e:
        logger.error(f"WS error for user {user_id}: {e}")
    finally:
        await emitter.disconnect(user_id, websocket)
        # Schedule pipeline stop with grace period if no more WebSocket connections
        # This allows brief disconnects (page navigation, network blips) without killing the stream
        if emitter.get_user_connection_count(user_id) == 0:
            from backend_v2.streaming.pipeline import schedule_pipeline_stop
            logger.info(f"Scheduling pipeline stop with grace period for user {user_id}")
            await schedule_pipeline_stop(user_id, grace_period_seconds=60)
