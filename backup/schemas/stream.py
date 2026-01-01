"""Pydantic schemas for streaming endpoints."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class StreamStartRequest(BaseModel):
    """Start stream request."""
    mood_id: Optional[str] = None
    context_name: Optional[str] = None
    resume: bool = False
    position_sec: Optional[float] = None  # For per-mood resume with custom position


class StreamStartResponse(BaseModel):
    """Start stream response."""
    session_id: str
    stream_url: str
    ws_url: str
    mood_id: Optional[str] = None  # Active mood ID
    now_playing: Optional[str] = None
    position_sec: Optional[float] = None  # Position to seek to on resume


class StreamStatusResponse(BaseModel):
    """Stream status response."""
    session_id: str
    active: bool
    mood_id: Optional[str]
    context_id: Optional[str]
    started_at: datetime
    now_playing: Optional[str] = None
