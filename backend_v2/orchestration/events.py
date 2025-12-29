"""User-scoped WebSocket event emitter.

Provides per-user event broadcasting to avoid leaking events between users.
All events are versioned with API version 2 (StatusEvents).

Event types:
- status: Structured StatusEvent for real-time progress updates (v2)
- now_playing: Current song info when it changes
- segment_ready: New segment available for playback
- decision_trace: AI decision reasoning (for debugging/transparency)
- dj_says: DJ speech script (for UI display)
- stream_status: Stream started/stopped notifications
"""
import asyncio
import json
import logging
import uuid
from collections import deque
from datetime import datetime
from typing import Dict, Set, Any, Optional, List

from fastapi import WebSocket

from backend_v2.schemas.status_events import (
    StatusEvent,
    StatusCategory,
    StatusStep,
    StatusEventPayload,
    Severity,
)

logger = logging.getLogger("ai-dj.events")

# Event API version (upgraded to 2 for StatusEvents)
EVENT_VERSION = 2

# Ring buffer size for event replay on reconnect
EVENT_RING_SIZE = 100

# Debug mode flag (set via environment or config)
DEBUG_MODE = True  # TODO: Make configurable


class UserEventEmitter:
    """Per-user WebSocket event emitter.
    
    Each user has their own set of WebSocket connections.
    Events are only broadcast to the specific user's connections.
    
    Features:
    - Structured StatusEvents for real-time progress
    - Ring buffer per user for event replay on reconnect
    - Non-blocking event emission
    """
    
    def __init__(self):
        # user_id -> set of WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        # user_id -> ring buffer of recent StatusEvents for replay
        self._event_ring: Dict[str, deque] = {}
        
    async def connect(self, user_id: str, websocket: WebSocket):
        """Register a WebSocket connection for a user.
        
        Args:
            user_id: The authenticated user's ID
            websocket: The WebSocket connection (already accepted)
        """
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)
            
        logger.info(f"WS connected: user {user_id} (total connections: {self.connection_count})")
        
    async def disconnect(self, user_id: str, websocket: WebSocket):
        """Unregister a WebSocket connection.
        
        Args:
            user_id: The user's ID
            websocket: The WebSocket connection to remove
        """
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].discard(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]
                    
        logger.info(f"WS disconnected: user {user_id} (total connections: {self.connection_count})")
        
    async def emit_to_user(
        self,
        user_id: str,
        event_type: str,
        data: Dict[str, Any],
        exclude: Optional[WebSocket] = None
    ):
        """Send an event to all of a user's connections.
        
        Args:
            user_id: The target user's ID
            event_type: Event type string (e.g., "now_playing")
            data: Event payload data
            exclude: Optional WebSocket to exclude from broadcast
        """
        event = {
            "v": EVENT_VERSION,
            "type": event_type,
            "data": data,
            "ts": datetime.utcnow().isoformat() + "Z"
        }
        
        message = json.dumps(event)
        disconnected = []
        
        async with self._lock:
            connections = self._connections.get(user_id, set()).copy()
            
        for ws in connections:
            if ws == exclude:
                continue
            try:
                await ws.send_text(message)
            except Exception as e:
                logger.debug(f"Failed to send to WS: {e}")
                disconnected.append(ws)
                
        # Clean up disconnected
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    if user_id in self._connections:
                        self._connections[user_id].discard(ws)
                        
    async def emit_now_playing(
        self,
        user_id: str,
        song_uuid: str,
        title: str,
        artist: str,
        artwork_url: Optional[str] = None
    ):
        """Emit a now_playing event."""
        await self.emit_to_user(user_id, "now_playing", {
            "song_uuid": song_uuid,
            "title": title,
            "artist": artist,
            "artwork_url": artwork_url,
        })
        
    async def emit_segment_ready(
        self,
        user_id: str,
        segment_index: int,
        duration_sec: float,
        song_uuid: Optional[str] = None
    ):
        """Emit a segment_ready event."""
        await self.emit_to_user(user_id, "segment_ready", {
            "segment_index": segment_index,
            "duration_sec": duration_sec,
            "song_uuid": song_uuid,
        })
        
    async def emit_decision_trace(
        self,
        user_id: str,
        agent_name: str,
        decision: str,
        rationale: Optional[str] = None
    ):
        """Emit a decision_trace event."""
        await self.emit_to_user(user_id, "decision_trace", {
            "agent": agent_name,
            "decision": decision,
            "rationale": rationale,
        })
        
    async def emit_dj_says(
        self,
        user_id: str,
        script: str
    ):
        """Emit a dj_says event (speech script for UI)."""
        await self.emit_to_user(user_id, "dj_says", {
            "script": script,
        })
        
    async def emit_stream_status(
        self,
        user_id: str,
        status: str,
        session_id: Optional[str] = None
    ):
        """Emit a stream_status event."""
        await self.emit_to_user(user_id, "stream_status", {
            "status": status,
            "session_id": session_id,
        })
    
    async def emit_status(
        self,
        user_id: str,
        category: StatusCategory,
        step: StatusStep,
        user_message: str,
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        progress: Optional[float] = None,
        eta_seconds: Optional[int] = None,
        debug_message: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        severity: Severity = Severity.INFO,
    ):
        """Emit a structured StatusEvent for real-time UI updates.
        
        Args:
            user_id: Target user
            category: Event category (generation, playback, etc.)
            step: Specific step/state within category
            user_message: Human-readable message for UI
            session_id: Optional session ID
            correlation_id: Optional ID linking related events
            progress: Optional progress 0.0-1.0
            eta_seconds: Optional estimated time remaining
            debug_message: Detailed message (only sent if DEBUG_MODE)
            payload: Optional structured data dict
            severity: Event severity level
        """
        event_id = str(uuid.uuid4())
        ts = datetime.utcnow()
        
        # Build payload model if dict provided
        event_payload = None
        if payload:
            event_payload = StatusEventPayload(**payload)
        
        # Create StatusEvent
        event = StatusEvent(
            id=event_id,
            ts=ts,
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
            category=category,
            step=step,
            progress=progress,
            eta_seconds=eta_seconds,
            user_message=user_message,
            debug_message=debug_message if DEBUG_MODE else None,
            payload=event_payload,
            severity=severity,
        )
        
        # Store in ring buffer for replay
        if user_id not in self._event_ring:
            self._event_ring[user_id] = deque(maxlen=EVENT_RING_SIZE)
        self._event_ring[user_id].append(event)
        
        # Auto-persist errors and major transitions to DB
        should_persist = (
            severity == Severity.ERROR or
            step in [StatusStep.ONBOARDING_COMPLETE, StatusStep.FAILED, StatusStep.STOPPED]
        )
        if should_persist:
            asyncio.create_task(self._persist_event_to_db(event))
        
        # Emit via WebSocket
        await self.emit_to_user(user_id, "status", event.model_dump(mode="json"))
        
        logger.debug(f"Status: {user_id} [{category.value}/{step.value}] {user_message}")
    
    async def _persist_event_to_db(self, event: StatusEvent):
        """Persist a StatusEvent to the database for observability.
        
        This runs as a background task to avoid blocking event emission.
        """
        try:
            from backend_v2.db.session import async_session_factory
            from backend_v2.models.status_event_log import StatusEventLog
            import json
            
            async with async_session_factory() as db:
                log_entry = StatusEventLog(
                    id=event.id,
                    user_id=event.user_id,
                    session_id=event.session_id,
                    correlation_id=event.correlation_id,
                    category=event.category.value,
                    step=event.step.value,
                    severity=event.severity.value,
                    user_message=event.user_message,
                    debug_message=event.debug_message,
                    progress=event.progress,
                    payload_json=json.dumps(event.payload.model_dump()) if event.payload else None,
                )
                db.add(log_entry)
                await db.commit()
                logger.debug(f"Persisted status event {event.id} to DB")
        except Exception as e:
            logger.error(f"Failed to persist status event: {e}")
    
    def get_events_since(self, user_id: str, last_event_id: Optional[str] = None) -> List[StatusEvent]:
        """Get events for replay on reconnect.
        
        Args:
            user_id: Target user
            last_event_id: If provided, only return events after this ID
            
        Returns:
            List of StatusEvents (may be empty if none stored)
        """
        if user_id not in self._event_ring:
            return []
        
        events = list(self._event_ring[user_id])
        
        if last_event_id:
            # Find the index of last_event_id and return events after it
            for i, event in enumerate(events):
                if event.id == last_event_id:
                    return events[i + 1:]
            # If not found, return all events
            
        return events
        
    def get_user_connection_count(self, user_id: str) -> int:
        """Get number of connections for a specific user."""
        return len(self._connections.get(user_id, set()))
        
    @property
    def connection_count(self) -> int:
        """Get total number of active connections."""
        return sum(len(conns) for conns in self._connections.values())
        
    @property
    def user_count(self) -> int:
        """Get number of users with active connections."""
        return len(self._connections)


# Global event emitter singleton
_event_emitter: Optional[UserEventEmitter] = None


def get_event_emitter() -> UserEventEmitter:
    """Get the global event emitter singleton."""
    global _event_emitter
    if _event_emitter is None:
        _event_emitter = UserEventEmitter()
    return _event_emitter
