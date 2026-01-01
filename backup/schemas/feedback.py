"""Pydantic schemas for feedback."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class FeedbackCreate(BaseModel):
    """Create feedback request."""
    song_uuid: Optional[str] = None
    track_title: Optional[str] = None
    track_artist: Optional[str] = None
    mood_id: Optional[str] = None
    value: str = Field(..., pattern=r'^(like|dislike)$')
    reason_text: Optional[str] = None


class FeedbackResponse(BaseModel):
    """Feedback response."""
    id: str
    song_uuid: Optional[str]
    track_title: Optional[str]
    track_artist: Optional[str]
    mood_id: Optional[str]
    value: str
    reason_text: Optional[str]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
