"""Pydantic schemas for moods."""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict


class MoodCreate(BaseModel):
    """Create mood request."""
    name: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    energy_target: Optional[float] = Field(None, ge=0.0, le=1.0)
    valence_target: Optional[float] = Field(None, ge=0.0, le=1.0)
    genres: Optional[List[str]] = None
    dj_personality: str = Field("chill", pattern=r'^(minimal|chill|chatty|casual_funny|minimal_talk|hype_energetic|light_roast|more_talk_between_songs)$')
    is_default: bool = False


class MoodUpdate(BaseModel):
    """Update mood request."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    energy_target: Optional[float] = Field(None, ge=0.0, le=1.0)
    valence_target: Optional[float] = Field(None, ge=0.0, le=1.0)
    genres: Optional[List[str]] = None
    dj_personality: Optional[str] = Field(None, pattern=r'^(minimal|chill|chatty|casual_funny|minimal_talk|hype_energetic|light_roast|more_talk_between_songs)$')


class MoodProfileResponse(BaseModel):
    """Mood profile response."""
    version: int
    summary_text: Optional[str]
    weights_json: Optional[str]
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class MoodResponse(BaseModel):
    """Mood response."""
    id: str
    name: str
    color: Optional[str]
    energy_target: Optional[float]
    valence_target: Optional[float]
    genres_json: Optional[str]
    dj_personality: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
    profile: Optional[MoodProfileResponse] = None
    
    model_config = ConfigDict(from_attributes=True)
